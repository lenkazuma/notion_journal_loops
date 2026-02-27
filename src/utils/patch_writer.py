"""
Generates review_patch.md — a human-readable diff/review file
showing which chunks are marked as duplicates and what changes
would be applied (strikethrough) before any writeback to Notion.
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional


def _notion_url(page_id: str) -> str:
    clean = page_id.replace("-", "")
    return f"https://www.notion.so/{clean}"


def write_review_patch(
    duplicates: List[Dict],
    output_path: Path,
    dry_run: bool = True,
) -> None:
    """
    Write a review_patch.md file.

    Parameters
    ----------
    duplicates : list of dicts with keys:
        dup_chunk_id, dup_page_id, dup_page_title, dup_date, dup_text,
        canonical_chunk_id, canonical_page_id, canonical_page_title,
        canonical_date, canonical_text, similarity
    output_path : Path to write the markdown file
    dry_run : if True, adds a banner noting no changes have been made
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)
    lines: List[str] = []

    lines.append("# Notion Journal Loops — Review Patch")
    lines.append(f"\nGenerated: {datetime.now().isoformat(timespec='seconds')}")
    if dry_run:
        lines.append("\n> **DRY-RUN MODE** — No changes have been written to Notion.")
    else:
        lines.append("\n> **LIVE MODE** — Changes have been (or will be) written to Notion.")

    lines.append(f"\nTotal duplicate chunks identified: **{len(duplicates)}**\n")
    lines.append("---\n")

    # Group by duplicate page
    by_page: Dict[str, List[Dict]] = {}
    for d in duplicates:
        pid = d["dup_page_id"]
        by_page.setdefault(pid, []).append(d)

    for page_id, entries in by_page.items():
        first = entries[0]
        page_title = first["dup_page_title"]
        page_url = _notion_url(page_id)

        lines.append(f"## Page: [{page_title}]({page_url})")
        lines.append(f"*Date: {first['dup_date']}*\n")

        for entry in entries:
            chunk_id = entry["dup_chunk_id"]
            sim = entry.get("similarity", 0.0)
            can_page_title = entry["canonical_page_title"]
            can_page_id = entry["canonical_page_id"]
            can_chunk_id = entry["canonical_chunk_id"]
            can_date = entry["canonical_date"]
            can_url = _notion_url(can_page_id)

            lines.append(f"### Chunk `{chunk_id}` (similarity: {sim:.4f})")
            lines.append(f"**Canonical:** [{can_page_title}]({can_url}) — chunk `{can_chunk_id}` (date: {can_date})\n")

            lines.append("**BEFORE (original text):**")
            lines.append("```")
            lines.append(entry["dup_text"][:800] + ("..." if len(entry["dup_text"]) > 800 else ""))
            lines.append("```\n")

            lines.append("**AFTER (with strikethrough + duplicate notice):**")
            lines.append("```")
            lines.append(f"(Duplicate of: [{can_page_title}]({can_url}) chunk {can_chunk_id})")
            lines.append("")
            # Show strikethrough in markdown
            dup_text_preview = entry["dup_text"][:800]
            lines.append(f"~~{dup_text_preview}~~")
            lines.append("```\n")
            lines.append("---\n")

    output_path.write_text("\n".join(lines), encoding="utf-8")


def write_duplicates_csv(
    duplicates: List[Dict],
    output_path: Path,
) -> None:
    """Write duplicates.csv with full duplicate mapping."""
    import csv

    output_path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "dup_chunk_id", "dup_page_id", "dup_page_title", "dup_date",
        "canonical_chunk_id", "canonical_page_id", "canonical_page_title",
        "canonical_date", "similarity",
    ]
    with output_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(duplicates)
