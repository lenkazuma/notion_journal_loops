"""
Step 4: Cluster embeddings using HDBSCAN or KMeans.
Output: data/clusters/cluster_assignments.json
"""
from __future__ import annotations

import json
import pickle
from typing import Dict, List, Optional, Tuple

import numpy as np
from sklearn.preprocessing import normalize

from src.config import (
    CLUSTER_METHOD,
    CLUSTERS_DIR,
    EMBEDDINGS_DIR,
    HDBSCAN_MIN_CLUSTER_SIZE,
    KMEANS_K_MAX,
    KMEANS_K_MIN,
)
from src.utils.logger import get_logger

logger = get_logger("pipeline.step4")

ASSIGNMENTS_CACHE = CLUSTERS_DIR / "cluster_assignments.json"


def _cluster_hdbscan(embeddings: np.ndarray, min_cluster_size: int) -> np.ndarray:
    """Cluster using HDBSCAN."""
    try:
        import hdbscan
    except ImportError:
        raise ImportError(
            "hdbscan is not installed. Run: pip install hdbscan"
        )

    logger.info(f"Running HDBSCAN (min_cluster_size={min_cluster_size})...")
    clusterer = hdbscan.HDBSCAN(
        min_cluster_size=min_cluster_size,
        min_samples=3,
        metric="euclidean",
        cluster_selection_method="eom",
    )
    # L2-normalize for cosine-like distance
    normed = normalize(embeddings, norm="l2")
    labels = clusterer.fit_predict(normed)
    n_clusters = len(set(labels)) - (1 if -1 in labels else 0)
    n_noise = int(np.sum(labels == -1))
    logger.info(f"HDBSCAN: {n_clusters} clusters, {n_noise} noise points")
    return labels


def _cluster_kmeans(embeddings: np.ndarray, k_min: int, k_max: int) -> np.ndarray:
    """Cluster using KMeans with automatic k selection via silhouette score."""
    from sklearn.cluster import KMeans
    from sklearn.metrics import silhouette_score, calinski_harabasz_score

    normed = normalize(embeddings, norm="l2")
    n_samples = len(embeddings)
    k_max = min(k_max, n_samples - 1)
    k_min = min(k_min, k_max)

    best_k = k_min
    best_score = -1.0
    best_labels = None

    logger.info(f"Searching KMeans k in [{k_min}, {k_max}]...")

    for k in range(k_min, k_max + 1):
        kmeans = KMeans(n_clusters=k, random_state=42, n_init=10)
        labels = kmeans.fit_predict(normed)
        if len(set(labels)) < 2:
            continue
        try:
            score = silhouette_score(normed, labels, sample_size=min(1000, n_samples))
        except Exception:
            score = calinski_harabasz_score(normed, labels) / 1000.0

        logger.debug(f"  k={k}: silhouette={score:.4f}")
        if score > best_score:
            best_score = score
            best_k = k
            best_labels = labels

    if best_labels is None:
        logger.warning("KMeans failed to find good k. Using k_min.")
        kmeans = KMeans(n_clusters=k_min, random_state=42, n_init=10)
        best_labels = kmeans.fit_predict(normed)

    logger.info(f"KMeans: best k={best_k}, silhouette={best_score:.4f}")
    return best_labels


def run(
    embeddings: Optional[np.ndarray] = None,
    chunk_ids: Optional[List[str]] = None,
    chunks: Optional[List[Dict]] = None,
    method: Optional[str] = None,
    force: bool = False,
) -> Dict[str, List[Dict]]:
    """
    Cluster embeddings and return cluster assignments.

    Parameters
    ----------
    embeddings : embedding matrix (loaded from cache if None)
    chunk_ids : list of chunk IDs (loaded from cache if None)
    chunks : list of chunk dicts (for enriching assignments)
    method : 'hdbscan' or 'kmeans' (uses config default if None)
    force : re-cluster even if cache exists

    Returns
    -------
    Dict mapping cluster_id -> list of chunk dicts
    """
    logger.info("=" * 60)
    logger.info("STEP 4: Clustering embeddings")
    logger.info("=" * 60)

    if not force and ASSIGNMENTS_CACHE.exists():
        logger.info(f"Loading cluster assignments from cache: {ASSIGNMENTS_CACHE}")
        assignments = json.loads(ASSIGNMENTS_CACHE.read_text(encoding="utf-8"))
        # Convert string keys back to int
        return {int(k): v for k, v in assignments.items()}

    # Load embeddings from cache if not provided
    if embeddings is None:
        emb_cache = EMBEDDINGS_DIR / "embeddings.pkl"
        ids_cache = EMBEDDINGS_DIR / "chunk_ids.json"
        if not emb_cache.exists():
            raise FileNotFoundError("No embeddings cache found. Run step 3 first.")
        embeddings = pickle.loads(emb_cache.read_bytes())
        chunk_ids = json.loads(ids_cache.read_text(encoding="utf-8"))

    if chunk_ids is None:
        raise ValueError("chunk_ids must be provided with embeddings")

    # Load chunks for enrichment
    if chunks is None:
        chunks_cache = EMBEDDINGS_DIR.parent / "chunks" / "chunks.json"
        if chunks_cache.exists():
            chunks = json.loads(chunks_cache.read_text(encoding="utf-8"))

    cluster_method = method or CLUSTER_METHOD

    if cluster_method == "hdbscan":
        labels = _cluster_hdbscan(embeddings, HDBSCAN_MIN_CLUSTER_SIZE)
    elif cluster_method == "kmeans":
        labels = _cluster_kmeans(embeddings, KMEANS_K_MIN, KMEANS_K_MAX)
    else:
        raise ValueError(f"Unknown cluster method: {cluster_method}. Use 'hdbscan' or 'kmeans'.")

    # Build chunk lookup
    chunk_lookup: Dict[str, Dict] = {}
    if chunks:
        chunk_lookup = {c["chunk_id"]: c for c in chunks}

    # Organize assignments
    cluster_assignments: Dict[int, List[Dict]] = {}
    for chunk_id, label in zip(chunk_ids, labels):
        label = int(label)
        if label not in cluster_assignments:
            cluster_assignments[label] = []
        chunk_data = chunk_lookup.get(chunk_id, {"chunk_id": chunk_id})
        chunk_data["cluster_id"] = label
        cluster_assignments[label].append(chunk_data)

    # Save cache
    ASSIGNMENTS_CACHE.write_text(
        json.dumps(cluster_assignments, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    n_clusters = len([k for k in cluster_assignments if k != -1])
    n_noise = len(cluster_assignments.get(-1, []))
    logger.info(f"Step 4 complete: {n_clusters} clusters, {n_noise} noise points")

    return cluster_assignments
