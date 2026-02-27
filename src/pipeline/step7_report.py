"""
Step 7: Generate final output reports.
Outputs:
  - data/outputs/report.md
  - data/outputs/report.json
  - data/outputs/cluster_assignments.csv
  - data/outputs/duplicates.csv
  - data/outputs/review_patch.md
"""
from __future__ import annotations

import csv
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from src.config import CLUSTERS_DIR, OUTPUTS_DIR
from src.utils.logger import get_logger
from src.utils.patch_writer import write_duplicates_csv, write_review_patch

logger = get_logger("pipeline.step7")


def _notion_url(page_id: str) -> str:
    clean = page_id.replace("-", "")
    return f"https://www.notion.so/{clean}"


def _write_report_md(
    summaries: List[Dict],
    cluster_assignments: Dict[int, List[Dict]],
    duplicates: List[Dict],
    output_path: Path,
) -> None:
    """Write the main markdown report."""
    lines = [
        "# Notion Journal Loops — Emotional Pattern Report",
        f"\nGenerated: {datetime.now().isoformat(timespec='seconds')}",
        f"\n**Total clusters:** {len([s for s in summaries if s['cluster_id'] != -1])}",
        f"**Total chunks analyzed:** {sum(len(v) for v in cluster_assignments.values())}",
        f"**Duplicate chunks detected:** {len(duplicates)}",
        "\n---\n",
    ]

    # Sort summaries by cluster_id
    sorted_summaries = sorted(summaries, key=lambda s: s["cluster_id"])

    for summary in sorted_summaries:
        cid = summary["cluster_id"]
        label = summary.get("label", "")
        chunk_count = summary.get("chunk_count", len(cluster_assignments.get(cid, [])))

        if cid == -1:
            lines.append(f"## Cluster -1: 噪声/未分类 ({chunk_count} chunks)")
        else:
            lines.append(f"## Cluster {cid}: {label} ({chunk_count} chunks)")

        loop_summary = summary.get("loop_summary", "")
        if loop_summary:
            lines.append(f"\n> {loop_summary}\n")

        emotions = summary.get("core_emotions", [])
        if emotions:
            lines.append(f"**核心情绪:** {' · '.join(emotions)}")

        triggers = summary.get("typical_triggers", [])
        if triggers:
            lines.append(f"**典型触发:** {' · '.join(triggers)}")

        thoughts = summary.get("automatic_thoughts", [])
        if thoughts:
            lines.append(f"**自动化思维:** {' · '.join(thoughts)}")

        behaviors = summary.get("behaviors", [])
        if behaviors:
            lines.append(f"**行为模式:** {' · '.join(behaviors)}")

        needs = summary.get("underlying_need", [])
        if needs:
            lines.append(f"**深层需求:** {' · '.join(needs)}")

        quotes = summary.get("representative_quotes", [])
        if quotes:
            lines.append("\n**代表性引用:**")
            for q in quotes[:6]:
                lines.append(f"- _{q}_")

        # Show sample pages in this cluster
        cluster_chunks = cluster_assignments.get(cid, [])
        if cluster_chunks:
            # Get unique pages
            pages_seen = set()
            page_list = []
            for chunk in cluster_chunks:
                pid = chunk.get("page_id", "")
                if pid and pid not in pages_seen:
                    pages_seen.add(pid)
                    page_list.append((chunk.get("page_title", ""), pid, chunk.get("page_date", "")))

            if page_list:
                lines.append(f"\n**相关页面 (共 {len(page_list)} 篇):**")
                for title, pid, date in sorted(page_list, key=lambda x: x[2])[:10]:
                    url = _notion_url(pid)
                    lines.append(f"- [{title}]({url}) — {date}")
                if len(page_list) > 10:
                    lines.append(f"- ... 及另外 {len(page_list) - 10} 篇")

        lines.append("\n---\n")

    # Duplicates summary
    if duplicates:
        lines.append("## 重复内容检测结果")
        lines.append(f"\n共检测到 **{len(duplicates)}** 个重复片段。")
        lines.append("详见 `data/outputs/duplicates.csv` 和 `data/outputs/review_patch.md`。\n")

        # Show top 5
        lines.append("**示例（前5条）:**")
        for d in duplicates[:5]:
            dup_url = _notion_url(d["dup_page_id"])
            can_url = _notion_url(d["canonical_page_id"])
            lines.append(
                f"- [{d['dup_page_title']}]({dup_url}) ({d['dup_date']}) chunk `{d['dup_chunk_id']}` "
                f"→ canonical: [{d['canonical_page_title']}]({can_url}) ({d['canonical_date']}) "
                f"(similarity: {d['similarity']:.4f})"
            )

    output_path.write_text("\n".join(lines), encoding="utf-8")
    logger.info(f"Report written: {output_path}")


def _write_cluster_csv(
    cluster_assignments: Dict[int, List[Dict]],
    output_path: Path,
) -> None:
    """Write cluster_assignments.csv."""
    fieldnames = ["chunk_id", "page_id", "page_title", "page_date", "cluster_id", "token_count"]
    with output_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for cluster_id, chunks in sorted(cluster_assignments.items()):
            for chunk in chunks:
                row = {k: chunk.get(k, "") for k in fieldnames}
                row["cluster_id"] = cluster_id
                writer.writerow(row)
    logger.info(f"Cluster CSV written: {output_path}")


def run(
    summaries: Optional[List[Dict]] = None,
    cluster_assignments: Optional[Dict[int, List[Dict]]] = None,
    duplicates: Optional[List[Dict]] = None,
    writeback_mode: str = "off",
    force: bool = False,
) -> None:
    """
    Generate all output reports.

    Parameters
    ----------
    summaries : cluster summaries (loaded from cache if None)
    cluster_assignments : {cluster_id: [chunk_dicts]} (loaded from cache if None)
    duplicates : list of duplicate records (loaded from cache if None)
    writeback_mode : 'off' | 'dryrun' | 'on'
    force : regenerate even if outputs exist
    """
    logger.info("=" * 60)
    logger.info("STEP 7: Generating reports")
    logger.info("=" * 60)

    # Load from cache if not provided
    if summaries is None:
        cache = CLUSTERS_DIR / "summaries.json"
        if cache.exists():
            summaries = json.loads(cache.read_text(encoding="utf-8"))
        else:
            logger.warning("No summaries found. Run step 5 first.")
            summaries = []

    if cluster_assignments is None:
        cache = CLUSTERS_DIR / "cluster_assignments.json"
        if cache.exists():
            raw = json.loads(cache.read_text(encoding="utf-8"))
            cluster_assignments = {int(k): v for k, v in raw.items()}
        else:
            logger.warning("No cluster assignments found. Run step 4 first.")
            cluster_assignments = {}

    if duplicates is None:
        cache = CLUSTERS_DIR / "duplicates.json"
        if cache.exists():
            duplicates = json.loads(cache.read_text(encoding="utf-8"))
        else:
            logger.warning("No duplicates found. Run step 6 first.")
            duplicates = []

    # Write report.md
    report_md = OUTPUTS_DIR / "report.md"
    _write_report_md(summaries, cluster_assignments, duplicates, report_md)

    # Write report.json
    report_json = OUTPUTS_DIR / "report.json"
    report_data = {
        "generated_at": datetime.now().isoformat(),
        "summaries": summaries,
        "total_chunks": sum(len(v) for v in cluster_assignments.values()),
        "total_duplicates": len(duplicates),
    }
    report_json.write_text(
        json.dumps(report_data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    logger.info(f"JSON report written: {report_json}")

    # Write cluster_assignments.csv
    cluster_csv = OUTPUTS_DIR / "cluster_assignments.csv"
    _write_cluster_csv(cluster_assignments, cluster_csv)

    # Write duplicates.csv
    if duplicates:
        dup_csv = OUTPUTS_DIR / "duplicates.csv"
        write_duplicates_csv(duplicates, dup_csv)
        logger.info(f"Duplicates CSV written: {dup_csv}")

    # Write review_patch.md
    if duplicates:
        patch_path = OUTPUTS_DIR / "review_patch.md"
        dry_run = writeback_mode != "on"
        write_review_patch(duplicates, patch_path, dry_run=dry_run)
        logger.info(f"Review patch written: {patch_path}")

    logger.info("Step 7 complete. All reports generated.")
    logger.info(f"Output directory: {OUTPUTS_DIR}")
