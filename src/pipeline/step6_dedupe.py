"""
Step 6: Detect duplicate/highly-similar chunks.
Strategy:
  - Cosine similarity on embeddings, computed in batches
  - Chunks from the same page are never paired with each other
  - "Earlier date wins" policy for canonical selection
Output: data/clusters/duplicates.json
"""
from __future__ import annotations

import json
import pickle
from typing import Dict, List, Optional

import numpy as np

from src.config import (
    CLUSTERS_DIR,
    DUP_CROSS_CLUSTER,
    DUP_SIM_THRESHOLD,
    EMBEDDINGS_DIR,
)
from src.utils.logger import get_logger

logger = get_logger("pipeline.step6")

DUPLICATES_CACHE = CLUSTERS_DIR / "duplicates.json"


def _parse_date(date_str: str) -> str:
    """Normalize date string to YYYY-MM-DD for comparison."""
    if not date_str:
        return "9999-12-31"  # Unknown dates sort last
    return date_str[:10]


def _make_record(chunk_a: Dict, chunk_b: Dict, sim: float) -> Dict:
    """Build a duplicate record; the chunk from the earlier page is canonical."""
    if _parse_date(chunk_a.get("page_date", "")) <= _parse_date(chunk_b.get("page_date", "")):
        canonical, duplicate = chunk_a, chunk_b
    else:
        canonical, duplicate = chunk_b, chunk_a
    return {
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
    }


def find_duplicates(
    chunks: List[Dict],
    labels: List[int],
    normed: np.ndarray,
    threshold: float,
    cross_cluster: bool = False,
    batch_size: int = 512,
) -> List[Dict]:
    """
    Return duplicate records for every pair of chunks with cosine similarity >= threshold.

    `normed` must hold L2-normalised embeddings in the same order as `chunks`/`labels`.
    Pairs from the same page are ignored (a page cannot duplicate itself), and pairs from
    different clusters are only reported when `cross_cluster` is True.
    Results are sorted by similarity, highest first.
    """
    n = len(chunks)
    if n < 2:
        return []

    label_arr = np.asarray(labels)
    page_ids = [c["page_id"] for c in chunks]
    records: List[Dict] = []

    for start in range(0, n, batch_size):
        block = normed[start:start + batch_size] @ normed.T
        rows, cols = np.nonzero(block >= threshold)
        for r, j in zip(rows.tolist(), cols.tolist()):
            i = start + r
            if j <= i or page_ids[i] == page_ids[j]:
                continue
            if not cross_cluster and label_arr[i] != label_arr[j]:
                continue
            records.append(_make_record(chunks[i], chunks[j], float(block[r, j])))

    records.sort(key=lambda d: d["similarity"], reverse=True)
    return records


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

    if chunk_ids is None:
        raise ValueError("chunk_ids must be provided together with embeddings.")
    chunk_id_to_idx: Dict[str, int] = {cid: i for i, cid in enumerate(chunk_ids)}

    all_chunks: List[Dict] = []
    labels: List[int] = []
    rows: List[int] = []
    for cluster_id, chunks in cluster_assignments.items():
        for chunk in chunks:
            idx = chunk_id_to_idx.get(chunk["chunk_id"])
            if idx is not None:
                all_chunks.append(chunk)
                labels.append(cluster_id)
                rows.append(idx)

    reordered = np.asarray(embeddings, dtype=np.float32)[rows] if rows else np.zeros((0, 1), dtype=np.float32)
    norms = np.linalg.norm(reordered, axis=1, keepdims=True)
    normed = reordered / np.where(norms == 0, 1e-10, norms)

    scope = "within and across clusters" if do_cross_cluster else "within clusters"
    logger.info(f"Running deduplication {scope} (threshold={sim_threshold})...")
    all_duplicates = find_duplicates(all_chunks, labels, normed, sim_threshold, do_cross_cluster)

    # Cache
    DUPLICATES_CACHE.write_text(
        json.dumps(all_duplicates, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    logger.info(f"Step 6 complete: {len(all_duplicates)} duplicate pairs detected.")
    return all_duplicates
