"""
Step 5: Summarize each cluster using LLM.
Output: data/clusters/summaries.json
"""
from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from src.config import CLUSTERS_DIR
from src.llm.embedder import get_provider
from src.llm.summarizer import summarize_all_clusters
from src.utils.logger import get_logger

logger = get_logger("pipeline.step5")


def run(
    cluster_assignments: Optional[Dict[int, List[Dict]]] = None,
    provider_name: Optional[str] = None,
    force: bool = False,
) -> List[Dict[str, Any]]:
    """
    Summarize all clusters.

    Parameters
    ----------
    cluster_assignments : {cluster_id: [chunk_dicts]} (loaded from cache if None)
    provider_name : override LLM provider
    force : re-summarize even if cache exists

    Returns
    -------
    List of summary dicts
    """
    logger.info("=" * 60)
    logger.info("STEP 5: Summarizing clusters")
    logger.info("=" * 60)

    if cluster_assignments is None:
        cache = CLUSTERS_DIR / "cluster_assignments.json"
        if not cache.exists():
            raise FileNotFoundError("No cluster assignments found. Run step 4 first.")
        raw = json.loads(cache.read_text(encoding="utf-8"))
        cluster_assignments = {int(k): v for k, v in raw.items()}

    provider = get_provider(provider_name)
    summaries = summarize_all_clusters(
        cluster_assignments=cluster_assignments,
        provider=provider,
        force=force,
    )

    logger.info(f"Step 5 complete: {len(summaries)} cluster summaries generated.")
    return summaries
