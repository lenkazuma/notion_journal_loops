"""
Step 1: Fetch all journal pages from Notion.
Output: data/raw/pages.json + data/raw/pages/{id}.json
"""
from __future__ import annotations

from typing import List, Dict, Optional

from src.notion.fetch_journal import fetch_all_pages
from src.utils.logger import get_logger

logger = get_logger("pipeline.step1")


def run(
    max_pages: Optional[int] = None,
    force: bool = False,
) -> List[Dict]:
    """
    Fetch all journal pages from Notion.

    Parameters
    ----------
    max_pages : limit number of pages (for testing)
    force : ignore cache and re-fetch

    Returns
    -------
    List of page records
    """
    logger.info("=" * 60)
    logger.info("STEP 1: Fetching journal pages from Notion")
    logger.info("=" * 60)

    from src.config import validate
    validate()

    pages = fetch_all_pages(max_pages=max_pages, force_refresh=force)
    logger.info(f"Step 1 complete: {len(pages)} pages fetched.")
    return pages
