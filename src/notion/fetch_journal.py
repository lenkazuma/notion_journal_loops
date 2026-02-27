"""
Fetch journal pages from Notion database.
Extracts: page_id, title, date, created_time, url, raw_text.
Caches results to data/raw/ as JSON files.
"""
from __future__ import annotations

import json
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from src.config import (
    NOTION_DATABASE_ID,
    NOTION_DATE_PROPERTY,
    NOTION_TITLE_PROPERTY,
    RAW_DIR,
)
from src.notion.blocks_to_text import blocks_to_text
from src.notion.client import paginate_blocks, paginate_database
from src.utils.logger import get_logger

logger = get_logger("notion.fetch_journal")

PAGES_CACHE = RAW_DIR / "pages.json"
PAGE_CONTENT_DIR = RAW_DIR / "pages"


def _extract_title(page: Dict[str, Any]) -> str:
    """Extract page title from properties."""
    props = page.get("properties", {})

    # Try configured title property first
    title_prop = props.get(NOTION_TITLE_PROPERTY, {})
    if title_prop:
        title_type = title_prop.get("type", "")
        if title_type == "title":
            rich = title_prop.get("title", [])
            text = "".join(rt.get("plain_text", "") for rt in rich)
            if text:
                return text.strip()

    # Fallback: find any property of type "title"
    for prop_name, prop_val in props.items():
        if prop_val.get("type") == "title":
            rich = prop_val.get("title", [])
            text = "".join(rt.get("plain_text", "") for rt in rich)
            if text:
                return text.strip()

    return f"Untitled ({page.get('id', '')[:8]})"


def _extract_date(page: Dict[str, Any]) -> str:
    """
    Extract date from the configured date property.
    Falls back to created_time.
    Returns ISO date string (YYYY-MM-DD).
    """
    props = page.get("properties", {})
    created = page.get("created_time", "")

    # Try configured date property
    date_prop = props.get(NOTION_DATE_PROPERTY, {})
    if date_prop:
        dtype = date_prop.get("type", "")
        if dtype == "date":
            date_obj = date_prop.get("date") or {}
            start = date_obj.get("start", "")
            if start:
                return start[:10]  # YYYY-MM-DD
        elif dtype == "created_time":
            val = date_prop.get("created_time", "")
            if val:
                return val[:10]
        elif dtype == "last_edited_time":
            val = date_prop.get("last_edited_time", "")
            if val:
                return val[:10]

    # Fallback to created_time
    if created:
        return created[:10]

    return ""


def _page_cache_path(page_id: str) -> Path:
    PAGE_CONTENT_DIR.mkdir(parents=True, exist_ok=True)
    return PAGE_CONTENT_DIR / f"{page_id}.json"


def fetch_page_content(page: Dict[str, Any], force: bool = False) -> Dict[str, Any]:
    """
    Fetch full text content for a single page.
    Caches result to data/raw/pages/{page_id}.json.
    """
    page_id = page["id"]
    cache_path = _page_cache_path(page_id)

    if not force and cache_path.exists():
        logger.debug(f"Cache hit for page {page_id}")
        return json.loads(cache_path.read_text(encoding="utf-8"))

    title = _extract_title(page)
    date = _extract_date(page)
    url = page.get("url", "")

    logger.info(f"Fetching content: [{title}] ({date})")

    try:
        blocks = paginate_blocks(page_id)
        raw_text = blocks_to_text(blocks, fetch_children=True)
    except Exception as e:
        logger.error(f"Failed to fetch blocks for page {page_id}: {e}")
        raw_text = ""

    record = {
        "page_id": page_id,
        "title": title,
        "date": date,
        "created_time": page.get("created_time", "")[:10],
        "url": url,
        "raw_text": raw_text,
    }

    cache_path.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
    time.sleep(0.3)  # Respect Notion rate limits
    return record


def fetch_all_pages(
    max_pages: Optional[int] = None,
    force_refresh: bool = False,
) -> List[Dict[str, Any]]:
    """
    Fetch all journal pages from the configured Notion database.
    Uses two-level cache:
      1. data/raw/pages.json — list of page metadata
      2. data/raw/pages/{id}.json — per-page content

    Parameters
    ----------
    max_pages : limit number of pages fetched (for testing)
    force_refresh : ignore cache and re-fetch everything

    Returns
    -------
    List of page records with: page_id, title, date, created_time, url, raw_text
    """
    if not force_refresh and PAGES_CACHE.exists():
        logger.info(f"Loading pages list from cache: {PAGES_CACHE}")
        pages_meta = json.loads(PAGES_CACHE.read_text(encoding="utf-8"))
    else:
        logger.info(f"Querying Notion database: {NOTION_DATABASE_ID}")
        raw_pages = paginate_database(
            database_id=NOTION_DATABASE_ID,
            max_pages=max_pages,
        )
        pages_meta = raw_pages
        PAGES_CACHE.write_text(
            json.dumps(pages_meta, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        logger.info(f"Saved {len(pages_meta)} pages to cache.")

    if max_pages:
        pages_meta = pages_meta[:max_pages]

    logger.info(f"Processing {len(pages_meta)} pages...")
    records: List[Dict[str, Any]] = []

    for i, page in enumerate(pages_meta):
        try:
            record = fetch_page_content(page, force=force_refresh)
            records.append(record)
            if (i + 1) % 20 == 0:
                logger.info(f"Progress: {i + 1}/{len(pages_meta)}")
        except Exception as e:
            logger.error(f"Skipping page {page.get('id', '?')}: {e}")

    logger.info(f"Successfully fetched {len(records)} pages.")
    return records
