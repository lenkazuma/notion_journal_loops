"""
Step 6: Detect duplicate/highly-similar chunks.
Strategy:
  - Primary: cosine similarity on embeddings
  - Auxiliary: SimHash pre-filter (optional)
  - "Earlier date wins" policy for canonical selection
Output: data/clusters/duplicates.json
"""
from __future__ import annotations

import json
import pickle
from typing import Dict, List, Optional, Tuple

import numpy as np

from src.config import (
    CLUSTERS_DIR,
    DUP_CROSS_CLUSTER,
    DUP_SIM_THRESHOLD,
    EMBEDDINGS_DIR,
)
from src.utils.logger import get_logger
from src.utils.similarity import batch_cosine_similarity, simhash, simhash_similarity

logger = get_logger("pipeline.step6")

DUPLICATES_CACHE = CLUSTERS_DIR / "duplicates.json"


def _parse_date(date_str: str) -> str:
    """Normalize date string to YYYY-MM-DD for comparison."""
    if not date_str:
        return "9999-12-31"  # Unknown dates sort last
    return date_str[:10]


def _find_duplicates_in_group(
    chunk_indices: List[int],
    all_chunks: List[Dict],
    embeddings: np.ndarray,
    threshold: float,
) -> List[Dict]:
    """
    Find duplicate pairs within a group of chunk indices.
    Returns list of duplicate records.
    """
    duplicates = []
    n = len(chunk_indices)

    if n < 2:
        return duplicates

    # Build sub-matrix
    sub_matrix = embeddings[chunk_indices]

    # Compare all pairs (upper triangle)
    for i in range(n):
        for j in range(i + 1, n):
            sim = float(np.dot(sub_matrix[i], sub_matrix[j]) /
                       (np.linalg.norm(sub_matrix[i]) * np.linalg.norm(sub_matrix[j]) + 1e-10))

            if sim >= threshold:
                idx_i = chunk_indices[i]
                idx_j = chunk_indices[j]
                chunk_i = all_chunks[idx_i]
                chunk_j = all_chunks[idx_j]

                date_i = _parse_date(chunk_i.get("page_date", ""))
                date_j = _parse_date(chunk_j.get("page_date", ""))

                # Earlier date = canonical
                if date_i <= date_j:
                    canonical, duplicate = chunk_i, chunk_j
                else:
                    canonical, duplicate = chunk_j, chunk_i

                duplicates.append({
                    "dup_chunk_id": duplicate["chunk_id"],
                    "dup_page_id": duplicate["page_id"],
                    "dup_page_title": duplicate.get("page_title", ""),
                    "dup_date": duplicate.get("page_date", ""),
                    "dup_text": duplicate.get("text", ""),
                    "canonical_chunk_id": canonical["chunk_id"],
                    "canonical_page_id": canonical["page_id"],
                    "canonical_page_title": canonical.get("page_title", ""),
                    "canonical_date": canonical.get("page_date", ""),
                    "canonical_text": canonical.get("text", ""),
                    "similarity": round(sim, 6),
                    "cluster_id": duplicate.get("cluster_id", -1),
                })

    return duplicates


def run(
    cluster_assignments: Optional[Dict[int, List[Dict]]] = None,
    embeddings: Optional[np.ndarray] = None,
    chunk_ids: Optional[List[str]] = None,
    threshold: Optional[float] = None,
    cross_cluster: Optional[bool] = None,
    force: bool = False,
) -> List[Dict]:
    """
    Detect duplicate chunks.

    Parameters
    ----------
    cluster_assignments : {cluster_id: [chunk_dicts]}
    embeddings : embedding matrix
    chunk_ids : list of chunk IDs (in same order as embeddings)
    threshold : cosine similarity threshold (uses config default if None)
    cross_cluster : also check across clusters (uses config default if None)
    force : re-run even if cache exists

    Returns
    -------
    List of duplicate records
    """
    logger.info("=" * 60)
    logger.info("STEP 6: Detecting duplicate chunks")
    logger.info("=" * 60)

    if not force and DUPLICATES_CACHE.exists():
        logger.info(f"Loading duplicates from cache: {DUPLICATES_CACHE}")
        dups = json.loads(DUPLICATES_CACHE.read_text(encoding="utf-8"))
        logger.info(f"Step 6 (cached): {len(dups)} duplicates loaded.")
        return dups

    sim_threshold = threshold if threshold is not None else DUP_SIM_THRESHOLD
    do_cross_cluster = cross_cluster if cross_cluster is not None else DUP_CROSS_CLUSTER

    # Load embeddings if not provided
    if embeddings is None:
        emb_cache = EMBEDDINGS_DIR / "embeddings.pkl"
        ids_cache = EMBEDDINGS_DIR / "chunk_ids.json"
        if not emb_cache.exists():
            raise FileNotFoundError("No embeddings cache. Run step 3 first.")
        embeddings = pickle.loads(emb_cache.read_bytes())
        chunk_ids = json.loads(ids_cache.read_text(encoding="utf-8"))

    # Load cluster assignments if not provided
    if cluster_assignments is None:
        cache = CLUSTERS_DIR / "cluster_assignments.json"
        if not cache.exists():
            raise FileNotFoundError("No cluster assignments. Run step 4 first.")
        raw = json.loads(cache.read_text(encoding="utf-8"))
        cluster_assignments = {int(k): v for k, v in raw.items()}

    # Build index: chunk_id -> position in embeddings array
    chunk_id_to_idx: Dict[str, int] = {cid: i for i, cid in enumerate(chunk_ids)}

    # Flatten all chunks with their embedding indices
    all_chunks: List[Dict] = []
    chunk_to_global_idx: Dict[str, int] = {}

    for cluster_id, chunks in cluster_assignments.items():
        for chunk in chunks:
            cid = chunk["chunk_id"]
            if cid in chunk_id_to_idx:
                global_idx = len(all_chunks)
                all_chunks.append(chunk)
                chunk_to_global_idx[cid] = global_idx

    # Rebuild embeddings in all_chunks order
    reordered_embeddings = np.zeros((len(all_chunks), embeddings.shape[1]), dtype=np.float32)
    for i, chunk in enumerate(all_chunks):
        cid = chunk["chunk_id"]
        if cid in chunk_id_to_idx:
            reordered_embeddings[i] = embeddings[chunk_id_to_idx[cid]]

    # L2-normalize
    norms = np.linalg.norm(reordered_embeddings, axis=1, keepdims=True)
    norms = np.where(norms == 0, 1e-10, norms)
    normed = reordered_embeddings / norms

    all_duplicates: List[Dict] = []
    seen_pairs = set()

    # Within-cluster deduplication (primary)
    logger.info(f"Running within-cluster deduplication (threshold={sim_threshold})...")
    for cluster_id, chunks in cluster_assignments.items():
        indices = [
            chunk_to_global_idx[c["chunk_id"]]
            for c in chunks
            if c["chunk_id"] in chunk_to_global_idx
        ]
        dups = _find_duplicates_in_group(indices, all_chunks, normed, sim_threshold)
        for d in dups:
            pair_key = tuple(sorted([d["dup_chunk_id"], d["canonical_chunk_id"]]))
            if pair_key not in seen_pairs:
                seen_pairs.add(pair_key)
                all_duplicates.append(d)

    logger.info(f"Within-cluster: {len(all_duplicates)} duplicates found")

    # Cross-cluster deduplication (optional)
    if do_cross_cluster:
        logger.info("Running cross-cluster deduplication (this may take a while)...")
        n = len(all_chunks)
        # Use batched approach to avoid memory explosion
        batch_size = 500
        for i in range(0, n, batch_size):
            query = normed[i]
            sims = normed.dot(query)
            # Find candidates above threshold (excluding self)
            candidates = np.where((sims >= sim_threshold) & (np.arange(n) != i))[0]
            for j in candidates:
                pair_key = tuple(sorted([all_chunks[i]["chunk_id"], all_chunks[j]["chunk_id"]]))
                if pair_key in seen_pairs:
                    continue
                seen_pairs.add(pair_key)
                chunk_i = all_chunks[i]
                chunk_j = all_chunks[j]
                # Skip if same cluster (already handled)
                if chunk_i.get("cluster_id") == chunk_j.get("cluster_id"):
                    continue
                date_i = _parse_date(chunk_i.get("page_date", ""))
                date_j = _parse_date(chunk_j.get("page_date", ""))
                if date_i <= date_j:
                    canonical, duplicate = chunk_i, chunk_j
                else:
                    canonical, duplicate = chunk_j, chunk_i
                all_duplicates.append({
                    "dup_chunk_id": duplicate["chunk_id"],
                    "dup_page_id": duplicate["page_id"],
                    "dup_page_title": duplicate.get("page_title", ""),
                    "dup_date": duplicate.get("page_date", ""),
                    "dup_text": duplicate.get("text", ""),
                    "canonical_chunk_id": canonical["chunk_id"],
                    "canonical_page_id": canonical["page_id"],
                    "canonical_page_title": canonical.get("page_title", ""),
                    "canonical_date": canonical.get("page_date", ""),
                    "canonical_text": canonical.get("text", ""),
                    "similarity": round(float(sims[j]), 6),
                    "cluster_id": duplicate.get("cluster_id", -1),
                })
        logger.info(f"Cross-cluster: total {len(all_duplicates)} duplicates")

    # Cache
    DUPLICATES_CACHE.write_text(
        json.dumps(all_duplicates, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    logger.info(f"Step 6 complete: {len(all_duplicates)} duplicate pairs detected.")
    return all_duplicates
