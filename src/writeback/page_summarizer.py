"""
Per-page summary writer.

For each journal page:
  1. Check if 'AI summary' property already has content → skip if so.
  2. Call LLM to generate a short (≤60 Chinese chars) summary of the page text.
  3. Write the summary back to the 'AI summary' rich_text property.

Usage:
    python -m src.writeback.page_summarizer [--mode dryrun|on] [--max-pages N] [--force]

Options:
    --mode      dryrun (default) | on
    --max-pages limit pages processed (for testing)
    --force     overwrite even if 'AI summary' already has content
    --concurrency N  parallel LLM calls (default 4, max 8)
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from dotenv import load_dotenv
load_dotenv(
    (Path(__file__).parent.parent.parent / ".env"),
    override=True,
)

from src.config import RAW_DIR
from src.llm.embedder import get_provider
from src.notion.client import get_client, update_page_properties
from src.utils.logger import get_logger
from src.utils.retry import api_retry

logger = get_logger("writeback.page_summarizer")

# Notion property name for the summary column
SUMMARY_PROPERTY = "AI summary"

# Max characters for the summary (Notion rich_text limit is 2000)
SUMMARY_MAX_CHARS = 150

SYSTEM_PROMPT = (
    "你是一个简洁的日记摘要助手。"
    "用不超过60个中文字（或120个英文字符）概括这篇日记的核心内容或情绪。"
    "直接输出摘要文本，不要加任何前缀、标签或引号。"
    "如果内容非常短或只是列表/备份，就用一句话描述其主题即可。"
    "如果内容只有图片链接（[image: ...]）或文件链接，输出：[图片/附件内容]"
    "如果内容是代码或技术记录，简要描述其用途。"
)


def _generate_summary(text: str, provider) -> str:
    """Call LLM to generate a short summary for one page."""
    # Trim input to avoid excessive tokens (keep first ~1500 chars)
    trimmed = text[:1500].strip()
    if not trimmed:
        return ""

    # Detect image/file-only pages — skip LLM call
    import re
    non_media = re.sub(r'\[(?:image|video|file|bookmark|pdf):[^\]]*\]', '', trimmed).strip()
    if not non_media:
        return "[图片/附件内容]"

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": trimmed},
    ]
    try:
        result = provider.chat(messages, temperature=0.3, max_tokens=120)
        # Trim to max chars
        return result.strip()[:SUMMARY_MAX_CHARS]
    except Exception as e:
        logger.error(f"LLM summary failed: {e}")
        return ""


def _get_existing_summary(page_id: str) -> str:
    """Fetch the current 'AI summary' value for a page from Notion."""
    client = get_client()
    try:
        page = client.pages.retrieve(page_id=page_id)
        prop = page.get("properties", {}).get(SUMMARY_PROPERTY, {})
        ptype = prop.get("type", "")
        if ptype == "rich_text":
            return "".join(r.get("plain_text", "") for r in prop.get("rich_text", []))
    except Exception as e:
        logger.warning(f"Could not fetch page {page_id}: {e}")
    return ""


def _write_summary(page_id: str, summary: str, mode: str) -> bool:
    """Write summary to Notion page. Returns True on success."""
    props = {
        SUMMARY_PROPERTY: {
            "rich_text": [{"type": "text", "text": {"content": summary}}]
        }
    }
    if mode == "on":
        try:
            update_page_properties(page_id, props)
            return True
        except Exception as e:
            logger.error(f"Failed to write summary for page {page_id}: {e}")
            return False
    else:
        return True  # dry-run always "succeeds"


def _process_one(
    record: Dict[str, Any],
    provider,
    mode: str,
    force: bool,
) -> Tuple[str, str, str]:
    """
    Process a single page record.
    Returns (page_id, title, status) where status is:
      'skipped'  — already has summary and force=False
      'written'  — summary generated and written (or dry-run)
      'empty'    — page has no text
      'error'    — something failed
    """
    page_id = record.get("page_id", "")
    title = record.get("title", "")
    raw_text = record.get("raw_text", "").strip()

    if not raw_text:
        return page_id, title, "empty"

    # Check existing summary (from Notion live, not cache)
    if not force:
        existing = _get_existing_summary(page_id)
        if existing.strip():
            logger.debug(f"Skip [{title}] — already has summary")
            return page_id, title, "skipped"

    # Generate summary
    summary = _generate_summary(raw_text, provider)
    if not summary:
        return page_id, title, "error"

    # Write back
    ok = _write_summary(page_id, summary, mode)
    if mode == "dryrun":
        logger.info(f"[DRY-RUN] [{title}] → {repr(summary)}")
    else:
        logger.info(f"[WRITTEN] [{title}] → {repr(summary)}")

    return page_id, title, "written" if ok else "error"


def run(
    mode: str = "dryrun",
    max_pages: Optional[int] = None,
    force: bool = False,
    concurrency: int = 4,
    provider_name: Optional[str] = None,
) -> Dict[str, int]:
    """
    Generate and write per-page summaries.

    Parameters
    ----------
    mode        : 'dryrun' | 'on'
    max_pages   : limit number of pages (for testing)
    force       : overwrite existing summaries
    concurrency : number of parallel LLM calls
    provider_name : override LLM provider

    Returns
    -------
    dict with counts: written, skipped, empty, error
    """
    if mode not in ("dryrun", "on"):
        raise ValueError(f"mode must be 'dryrun' or 'on', got: {mode!r}")

    logger.info(f"Page summarizer — mode={mode.upper()}, force={force}")
    if mode == "on":
        logger.warning("LIVE MODE: Summaries will be written to Notion.")

    # Load all page records from cache
    pages_dir = RAW_DIR / "pages"
    if not pages_dir.exists():
        raise FileNotFoundError("No page cache found. Run step 1 first.")

    records: List[Dict] = []
    for json_file in sorted(pages_dir.glob("*.json")):
        try:
            records.append(json.loads(json_file.read_text(encoding="utf-8")))
        except Exception:
            pass

    if not records:
        raise FileNotFoundError("No page records found in data/raw/pages/")

    if max_pages:
        records = records[:max_pages]

    logger.info(f"Processing {len(records)} pages (concurrency={concurrency})...")

    provider = get_provider(provider_name)
    counts = {"written": 0, "skipped": 0, "empty": 0, "error": 0}

    # Use thread pool for parallel LLM calls
    # Rate-limit: add small sleep between writes to respect Notion limits
    with ThreadPoolExecutor(max_workers=concurrency) as executor:
        futures = {
            executor.submit(_process_one, rec, provider, mode, force): rec
            for rec in records
        }
        done = 0
        for future in as_completed(futures):
            try:
                page_id, title, status = future.result()
                counts[status] = counts.get(status, 0) + 1
            except Exception as e:
                counts["error"] += 1
                logger.error(f"Unexpected error: {e}")
            done += 1
            if done % 20 == 0:
                logger.info(f"Progress: {done}/{len(records)} — {counts}")
            # Small sleep to avoid Notion rate limits on writes
            if mode == "on" and done % 5 == 0:
                time.sleep(0.5)

    logger.info(f"Done. Results: {counts}")
    return counts


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Generate short AI summaries for each journal page and write to Notion."
    )
    parser.add_argument(
        "--mode", type=str, choices=["dryrun", "on"], default="dryrun",
        help="dryrun (default): preview only. on: write to Notion.",
    )
    parser.add_argument(
        "--max-pages", type=int, default=None, metavar="N",
        help="Limit number of pages processed (for testing).",
    )
    parser.add_argument(
        "--force", action="store_true",
        help="Overwrite existing summaries.",
    )
    parser.add_argument(
        "--concurrency", type=int, default=4, metavar="N",
        help="Parallel LLM calls (default: 4).",
    )
    parser.add_argument(
        "--provider", type=str, default=None,
        choices=["openai", "anthropic", "fallback"],
        help="LLM provider override.",
    )
    args = parser.parse_args(argv)

    try:
        counts = run(
            mode=args.mode,
            max_pages=args.max_pages,
            force=args.force,
            concurrency=args.concurrency,
            provider_name=args.provider,
        )
        total = sum(counts.values())
        logger.info(
            f"Summary: {counts['written']} written, "
            f"{counts['skipped']} skipped (already had summary), "
            f"{counts['empty']} empty pages, "
            f"{counts['error']} errors / {total} total"
        )
        return 0 if counts["error"] == 0 else 1
    except Exception as e:
        logger.exception(f"Page summarizer failed: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
