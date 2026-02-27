"""
Cluster summarizer: calls LLM to generate structured JSON summaries
for each cluster, identifying emotional loops and recurring patterns.
"""
from __future__ import annotations

import json
import random
from typing import Any, Dict, List, Optional

from src.config import SUMMARY_SAMPLE_PER_CLUSTER
from src.llm.provider_base import ProviderBase
from src.utils.logger import get_logger

logger = get_logger("llm.summarizer")

SYSTEM_PROMPT = """你是一位资深心理咨询师与数据分析师，专门分析日记/日志中的情绪模式与认知循环。
你的任务是分析给定的日记片段集合，识别其中的"情绪循环/重复模式（recurring emotional loops）"。

请严格按照以下 JSON 格式输出，不要添加任何额外文字：
{
  "cluster_id": <int>,
  "label": "<简洁的模式标签，10字以内>",
  "core_emotions": ["<情绪1>", "<情绪2>", ...],
  "typical_triggers": ["<触发因素1>", ...],
  "automatic_thoughts": ["<自动化思维1>", ...],
  "behaviors": ["<行为模式1>", ...],
  "underlying_need": ["<深层需求1>", ...],
  "loop_summary": "<一段话总结这个情绪循环，100字以内>",
  "representative_quotes": ["<原文短句1（≤20字）>", ...],
  "related_clusters": []
}"""


def _build_user_prompt(cluster_id: int, chunks: List[Dict]) -> str:
    """Build the user prompt for cluster summarization."""
    # Sample if too many chunks
    sample = chunks
    if len(chunks) > SUMMARY_SAMPLE_PER_CLUSTER:
        sample = random.sample(chunks, SUMMARY_SAMPLE_PER_CLUSTER)
        logger.debug(f"Cluster {cluster_id}: sampled {len(sample)}/{len(chunks)} chunks")

    entries = []
    for i, chunk in enumerate(sample):
        date = chunk.get("page_date", "")
        title = chunk.get("page_title", "")
        text = chunk.get("text", "")[:600]  # Limit per chunk
        entries.append(f"[{i+1}] ({date}) {title}\n{text}")

    joined = "\n\n---\n\n".join(entries)
    return (
        f"以下是来自日记数据库的第 {cluster_id} 组（共 {len(chunks)} 条）日记片段，"
        f"请分析其中的情绪循环与重复模式：\n\n{joined}"
    )


def summarize_cluster(
    cluster_id: int,
    chunks: List[Dict],
    provider: ProviderBase,
) -> Dict[str, Any]:
    """
    Summarize a single cluster using the LLM provider.

    Returns a structured dict matching the JSON schema above.
    """
    if not chunks:
        return _empty_summary(cluster_id)

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": _build_user_prompt(cluster_id, chunks)},
    ]

    try:
        result = provider.chat_json(messages, temperature=0.3, max_tokens=1500)
        # Ensure result is a dict (LLM might return a list in rare cases)
        if isinstance(result, list):
            result = result[0] if result else {}
        if not isinstance(result, dict):
            raise ValueError(f"Expected dict from LLM, got {type(result)}")
        result["cluster_id"] = cluster_id
        result["chunk_count"] = len(chunks)
        return result
    except Exception as e:
        logger.error(f"Failed to summarize cluster {cluster_id}: {e}")
        summary = _empty_summary(cluster_id)
        summary["error"] = str(e)
        return summary


def summarize_all_clusters(
    cluster_assignments: Dict[int, List[Dict]],
    provider: ProviderBase,
    force: bool = False,
) -> List[Dict[str, Any]]:
    """
    Summarize all clusters.

    Parameters
    ----------
    cluster_assignments : {cluster_id: [chunk_dicts]}
    provider : LLM provider
    force : re-summarize even if cached

    Returns
    -------
    List of summary dicts
    """
    from src.config import CLUSTERS_DIR
    cache_path = CLUSTERS_DIR / "summaries.json"

    if not force and cache_path.exists():
        logger.info("Loading cluster summaries from cache...")
        return json.loads(cache_path.read_text(encoding="utf-8"))

    summaries = []
    cluster_ids = sorted(k for k in cluster_assignments.keys() if k != -1)
    noise_chunks = cluster_assignments.get(-1, [])

    logger.info(f"Summarizing {len(cluster_ids)} clusters (noise: {len(noise_chunks)} chunks)...")

    for cluster_id in cluster_ids:
        chunks = cluster_assignments[cluster_id]
        logger.info(f"Summarizing cluster {cluster_id} ({len(chunks)} chunks)...")
        summary = summarize_cluster(cluster_id, chunks, provider)
        summaries.append(summary)

    # Add noise cluster summary if exists
    if noise_chunks:
        noise_summary = {
            "cluster_id": -1,
            "label": "噪声/未分类",
            "core_emotions": [],
            "typical_triggers": [],
            "automatic_thoughts": [],
            "behaviors": [],
            "underlying_need": [],
            "loop_summary": f"共 {len(noise_chunks)} 条未被聚类的片段（HDBSCAN噪声点）。",
            "representative_quotes": [],
            "related_clusters": [],
            "chunk_count": len(noise_chunks),
        }
        summaries.append(noise_summary)

    # Cache
    cache_path.write_text(
        json.dumps(summaries, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    logger.info(f"Saved {len(summaries)} summaries to {cache_path}")
    return summaries


def _empty_summary(cluster_id: int) -> Dict[str, Any]:
    return {
        "cluster_id": cluster_id,
        "label": "空聚类",
        "core_emotions": [],
        "typical_triggers": [],
        "automatic_thoughts": [],
        "behaviors": [],
        "underlying_need": [],
        "loop_summary": "该聚类为空或无法生成摘要。",
        "representative_quotes": [],
        "related_clusters": [],
        "chunk_count": 0,
    }
