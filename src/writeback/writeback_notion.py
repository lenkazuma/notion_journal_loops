"""
Writeback to Notion: apply cluster labels, duplicate markers, and strikethrough.

Modes:
  off    — do nothing (default)
  dryrun — print what would be done + write review_patch.md
  on     — actually write to Notion

Usage:
    python -m src.writeback.writeback_notion [--mode off|dryrun|on]

IMPORTANT: Always review review_patch.md before switching to --mode on.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from src.config import (
    CLUSTERS_DIR,
    OUTPUTS_DIR,
    WRITEBACK_MODE,
)
from src.notion.client import (
    append_block_children,
    paginate_blocks,
    update_page_properties,
)
from src.utils.logger import get_logger
from src.utils.patch_writer import write_review_patch

logger = get_logger("writeback")


# ── Property builders ────────────────────────────────────────────────────────

def _build_cluster_properties(cluster_id: int, loop_label: str) -> Dict[str, Any]:
    """Build Notion property update dict for cluster info."""
    return {
        "ClusterId": {"number": cluster_id},
        "LoopLabel": {
            "rich_text": [{"type": "text", "text": {"content": loop_label[:2000]}}]
        },
    }


def _build_duplicate_properties(
    canonical_page_id: str,
    canonical_chunk_id: str,
) -> Dict[str, Any]:
    """Build Notion property update dict for duplicate marking."""
    canonical_url = f"https://www.notion.so/{canonical_page_id.replace('-', '')}"
    return {
        "IsDuplicate": {"checkbox": True},
        "CanonicalPage": {"url": canonical_url},
        "CanonicalChunk": {
            "rich_text": [{"type": "text", "text": {"content": canonical_chunk_id[:2000]}}]
        },
    }


def _build_strikethrough_blocks(
    dup_text: str,
    canonical_page_id: str,
    canonical_chunk_id: str,
    canonical_page_title: str,
) -> List[Dict]:
    """
    Build Notion block children to insert before a duplicate section:
    1. A notice paragraph: "(Duplicate of: <canonical link>)"
    2. The original text with strikethrough annotation applied.
    """
    canonical_url = f"https://www.notion.so/{canonical_page_id.replace('-', '')}"

    # Notice block
    notice_block = {
        "object": "block",
        "type": "paragraph",
        "paragraph": {
            "rich_text": [
                {
                    "type": "text",
                    "text": {"content": "(Duplicate of: "},
                    "annotations": {"bold": True, "color": "red"},
                },
                {
                    "type": "text",
                    "text": {
                        "content": canonical_page_title or canonical_page_id,
                        "link": {"url": canonical_url},
                    },
                    "annotations": {"bold": True, "color": "red"},
                },
                {
                    "type": "text",
                    "text": {"content": f" — chunk {canonical_chunk_id})"},
                    "annotations": {"bold": True, "color": "red"},
                },
            ]
        },
    }

    # Strikethrough text blocks (Notion has 2000 char limit per rich_text element)
    text_blocks = []
    chunk_size = 1800
    for i in range(0, len(dup_text), chunk_size):
        piece = dup_text[i: i + chunk_size]
        text_blocks.append({
            "object": "block",
            "type": "paragraph",
            "paragraph": {
                "rich_text": [
                    {
                        "type": "text",
                        "text": {"content": piece},
                        "annotations": {"strikethrough": True, "color": "gray"},
                    }
                ]
            },
        })

    return [notice_block] + text_blocks


# ── Core writeback functions ─────────────────────────────────────────────────

def apply_cluster_labels(
    cluster_assignments: Dict[int, List[Dict]],
    summaries: List[Dict],
    mode: str,
) -> int:
    """
    Apply ClusterId and LoopLabel properties to Notion pages.
    Returns count of pages updated.
    """
    # Build cluster_id -> label mapping
    label_map = {s["cluster_id"]: s.get("label", "") for s in summaries}

    # Collect unique pages and their cluster info
    page_clusters: Dict[str, Dict] = {}
    for cluster_id, chunks in cluster_assignments.items():
        label = label_map.get(cluster_id, "")
        for chunk in chunks:
            pid = chunk.get("page_id", "")
            if pid and pid not in page_clusters:
                page_clusters[pid] = {"cluster_id": cluster_id, "label": label}

    count = 0
    for page_id, info in page_clusters.items():
        props = _build_cluster_properties(info["cluster_id"], info["label"])
        if mode == "on":
            try:
                update_page_properties(page_id, props)
                count += 1
                time.sleep(0.35)
            except Exception as e:
                logger.error(f"Failed to update page {page_id}: {e}")
        else:
            logger.info(f"[DRY-RUN] Would update page {page_id}: ClusterId={info['cluster_id']}, LoopLabel={info['label']}")
            count += 1

    return count


def apply_duplicate_markers(
    duplicates: List[Dict],
    mode: str,
) -> int:
    """
    Apply IsDuplicate, CanonicalPage, CanonicalChunk properties to duplicate pages.
    Also inserts strikethrough blocks for duplicate text.
    Returns count of pages updated.
    """
    # Group by page
    by_page: Dict[str, List[Dict]] = {}
    for d in duplicates:
        pid = d["dup_page_id"]
        by_page.setdefault(pid, []).append(d)

    count = 0
    for page_id, entries in by_page.items():
        # Use first entry for canonical info (page-level)
        first = entries[0]
        props = _build_duplicate_properties(
            first["canonical_page_id"],
            first["canonical_chunk_id"],
        )

        if mode == "on":
            try:
                update_page_properties(page_id, props)
                time.sleep(0.35)

                # Insert strikethrough blocks for each duplicate chunk
                for entry in entries:
                    blocks = _build_strikethrough_blocks(
                        dup_text=entry["dup_text"][:3600],
                        canonical_page_id=entry["canonical_page_id"],
                        canonical_chunk_id=entry["canonical_chunk_id"],
                        canonical_page_title=entry["canonical_page_title"],
                    )
                    try:
                        append_block_children(page_id, blocks)
                        time.sleep(0.35)
                    except Exception as e:
                        logger.error(f"Failed to append blocks to page {page_id}: {e}")

                count += 1
            except Exception as e:
                logger.error(f"Failed to update duplicate page {page_id}: {e}")
        else:
            logger.info(
                f"[DRY-RUN] Would mark page {page_id} as duplicate of "
                f"{first['canonical_page_id']} ({len(entries)} chunks)"
            )
            count += 1

    return count


# ── Main entry point ─────────────────────────────────────────────────────────

def run(mode: Optional[str] = None) -> None:
    """
    Run the writeback process.

    Parameters
    ----------
    mode : 'off' | 'dryrun' | 'on' (uses WRITEBACK_MODE from config if None)
    """
    effective_mode = mode or WRITEBACK_MODE

    if effective_mode == "off":
        logger.info("Writeback mode is 'off'. Nothing to do.")
        logger.info("Set --writeback-mode dryrun to preview changes.")
        return

    logger.info(f"Writeback mode: {effective_mode.upper()}")
    if effective_mode == "on":
        logger.warning(
            "LIVE MODE: Changes will be written to Notion. "
            "Make sure you have reviewed review_patch.md first!"
        )

    # Load data
    summaries_path = CLUSTERS_DIR / "summaries.json"
    assignments_path = CLUSTERS_DIR / "cluster_assignments.json"
    duplicates_path = CLUSTERS_DIR / "duplicates.json"

    if not assignments_path.exists():
        logger.error("No cluster assignments found. Run the full pipeline first.")
        return

    summaries = json.loads(summaries_path.read_text(encoding="utf-8")) if summaries_path.exists() else []
    raw_assignments = json.loads(assignments_path.read_text(encoding="utf-8"))
    cluster_assignments = {int(k): v for k, v in raw_assignments.items()}
    duplicates = json.loads(duplicates_path.read_text(encoding="utf-8")) if duplicates_path.exists() else []

    # Always write review patch first
    if duplicates:
        patch_path = OUTPUTS_DIR / "review_patch.md"
        write_review_patch(duplicates, patch_path, dry_run=(effective_mode != "on"))
        logger.info(f"Review patch written: {patch_path}")

    # Apply cluster labels
    logger.info("Applying cluster labels to pages...")
    n_cluster = apply_cluster_labels(cluster_assignments, summaries, effective_mode)
    logger.info(f"Cluster labels: {n_cluster} pages {'updated' if effective_mode == 'on' else 'would be updated'}")

    # Apply duplicate markers
    if duplicates:
        logger.info("Applying duplicate markers to pages...")
        n_dup = apply_duplicate_markers(duplicates, effective_mode)
        logger.info(f"Duplicate markers: {n_dup} pages {'updated' if effective_mode == 'on' else 'would be updated'}")

    if effective_mode == "dryrun":
        logger.info("DRY-RUN complete. Review the output above and review_patch.md.")
        logger.info("To apply changes: python -m src.writeback.writeback_notion --mode on")
    else:
        logger.info("Writeback complete.")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Write cluster labels and duplicate markers back to Notion."
    )
    parser.add_argument(
        "--mode",
        type=str,
        choices=["off", "dryrun", "on"],
        default=None,
        help="Writeback mode (default: uses WRITEBACK_MODE from .env)",
    )
    args = parser.parse_args(argv)

    try:
        run(mode=args.mode)
        return 0
    except Exception as e:
        logger.exception(f"Writeback failed: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
