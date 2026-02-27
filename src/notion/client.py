"""
Notion API client wrapper with retry logic.
Compatible with notion-client v3 (data_sources.query replaces databases.query).
"""
from __future__ import annotations

import time
from typing import Any, Dict, List, Optional

from notion_client import Client
from notion_client.errors import APIResponseError

from src.config import NOTION_TOKEN
from src.utils.logger import get_logger
from src.utils.retry import api_retry

logger = get_logger("notion.client")

_client: Optional[Client] = None


def get_client() -> Client:
    """Return a singleton Notion client."""
    global _client
    if _client is None:
        if not NOTION_TOKEN:
            raise ValueError("NOTION_TOKEN is not configured.")
        _client = Client(auth=NOTION_TOKEN)
    return _client


@api_retry(max_attempts=6, min_wait=1.0, max_wait=60.0)
def query_database(
    database_id: str,
    filter_obj: Optional[Dict] = None,
    sorts: Optional[List[Dict]] = None,
    page_size: int = 100,
    start_cursor: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Query a Notion database (single page of results).
    notion-client v3: uses data_sources.query instead of databases.query.
    """
    client = get_client()
    kwargs: Dict[str, Any] = {
        "data_source_id": database_id,
        "page_size": page_size,
    }
    if filter_obj:
        kwargs["filter"] = filter_obj
    if sorts:
        kwargs["sorts"] = sorts
    if start_cursor:
        kwargs["start_cursor"] = start_cursor
    return client.data_sources.query(**kwargs)


@api_retry(max_attempts=6, min_wait=1.0, max_wait=60.0)
def get_block_children(block_id: str, start_cursor: Optional[str] = None) -> Dict[str, Any]:
    """Fetch children blocks of a page/block."""
    client = get_client()
    kwargs: Dict[str, Any] = {"block_id": block_id, "page_size": 100}
    if start_cursor:
        kwargs["start_cursor"] = start_cursor
    return client.blocks.children.list(**kwargs)


@api_retry(max_attempts=6, min_wait=1.0, max_wait=60.0)
def update_page_properties(page_id: str, properties: Dict[str, Any]) -> Dict[str, Any]:
    """Update properties on a Notion page."""
    client = get_client()
    return client.pages.update(page_id=page_id, properties=properties)


@api_retry(max_attempts=6, min_wait=1.0, max_wait=60.0)
def append_block_children(page_id: str, children: List[Dict]) -> Dict[str, Any]:
    """Append block children to a page."""
    client = get_client()
    return client.blocks.children.append(block_id=page_id, children=children)


@api_retry(max_attempts=6, min_wait=1.0, max_wait=60.0)
def update_block(block_id: str, block_data: Dict[str, Any]) -> Dict[str, Any]:
    """Update a specific block."""
    client = get_client()
    return client.blocks.update(block_id=block_id, **block_data)


def paginate_database(
    database_id: str,
    filter_obj: Optional[Dict] = None,
    sorts: Optional[List[Dict]] = None,
    max_pages: Optional[int] = None,
) -> List[Dict[str, Any]]:
    """
    Fetch ALL pages from a Notion database using cursor-based pagination.

    Parameters
    ----------
    database_id : Notion database ID
    filter_obj : optional Notion filter object
    sorts : optional sort spec
    max_pages : if set, stop after fetching this many Notion pages

    Returns
    -------
    List of Notion page objects
    """
    results: List[Dict[str, Any]] = []
    cursor: Optional[str] = None

    while True:
        response = query_database(
            database_id=database_id,
            filter_obj=filter_obj,
            sorts=sorts,
            start_cursor=cursor,
        )
        batch = response.get("results", [])
        results.extend(batch)
        logger.info(f"Fetched {len(batch)} pages (total so far: {len(results)})")

        if max_pages and len(results) >= max_pages:
            results = results[:max_pages]
            break

        if not response.get("has_more"):
            break
        cursor = response.get("next_cursor")
        # Respect rate limits
        time.sleep(0.35)

    return results


def paginate_blocks(page_id: str) -> List[Dict[str, Any]]:
    """Fetch ALL blocks for a page, handling pagination."""
    blocks: List[Dict[str, Any]] = []
    cursor: Optional[str] = None

    while True:
        response = get_block_children(page_id, start_cursor=cursor)
        batch = response.get("results", [])
        blocks.extend(batch)

        if not response.get("has_more"):
            break
        cursor = response.get("next_cursor")
        time.sleep(0.2)

    return blocks
