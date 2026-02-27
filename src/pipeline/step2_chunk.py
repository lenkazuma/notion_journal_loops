"""
Step 2: Chunk all page texts into manageable segments.
Output: data/chunks/chunks.json
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List, Optional

from src.config import CHUNK_MAX_TOKENS, CHUNK_TARGET_TOKENS, CHUNKS_DIR
from src.utils.logger import get_logger
from src.utils.text_chunker import Chunk, chunk_text

logger = get_logger("pipeline.step2")

CHUNKS_CACHE = CHUNKS_DIR / "chunks.json"


def run(
    pages: Optional[List[Dict]] = None,
    force: bool = False,
) -> List[Dict]:
    """
    Chunk all page texts.

    Parameters
    ----------
    pages : list of page records (loaded from cache if None)
    force : re-chunk even if cache exists

    Returns
    -------
    List of chunk dicts
    """
    logger.info("=" * 60)
    logger.info("STEP 2: Chunking page texts")
    logger.info("=" * 60)

    if not force and CHUNKS_CACHE.exists():
        logger.info(f"Loading chunks from cache: {CHUNKS_CACHE}")
        chunks = json.loads(CHUNKS_CACHE.read_text(encoding="utf-8"))
        logger.info(f"Step 2 (cached): {len(chunks)} chunks loaded.")
        return chunks

    if pages is None:
        from src.config import RAW_DIR
        pages_cache = RAW_DIR / "pages.json"
        if not pages_cache.exists():
            raise FileNotFoundError(
                "No pages cache found. Run step 1 first: "
                "python -m src.pipeline.run_pipeline --from-step 1"
            )
        raw_pages = json.loads(pages_cache.read_text(encoding="utf-8"))
        # Load full content for each page
        pages_dir = RAW_DIR / "pages"
        pages = []
        for p in raw_pages:
            pid = p["id"] if "id" in p else p.get("page_id", "")
            content_path = pages_dir / f"{pid}.json"
            if content_path.exists():
                pages.append(json.loads(content_path.read_text(encoding="utf-8")))

    all_chunks: List[Dict] = []
    skipped = 0

    for page in pages:
        page_id = page.get("page_id", "")
        title = page.get("title", "Untitled")
        date = page.get("date", "")
        text = page.get("raw_text", "")

        if not text or not text.strip():
            skipped += 1
            logger.debug(f"Skipping empty page: {title}")
            continue

        chunks = chunk_text(
            text=text,
            page_id=page_id,
            page_title=title,
            page_date=date,
            target_tokens=CHUNK_TARGET_TOKENS,
            max_tokens=CHUNK_MAX_TOKENS,
        )

        for chunk in chunks:
            all_chunks.append({
                "chunk_id": chunk.chunk_id,
                "page_id": chunk.page_id,
                "page_title": chunk.page_title,
                "page_date": chunk.page_date,
                "chunk_index": chunk.chunk_index,
                "text": chunk.text,
                "token_count": chunk.token_count,
            })

    logger.info(
        f"Step 2 complete: {len(all_chunks)} chunks from {len(pages) - skipped} pages "
        f"({skipped} pages skipped - empty)."
    )

    CHUNKS_CACHE.write_text(
        json.dumps(all_chunks, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return all_chunks
