"""
Text chunking utilities.
Strategy: split by natural paragraphs first; merge short paragraphs;
split long paragraphs by sentences or characters to stay within token limits.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List

from src.utils.token_estimator import estimate_tokens


@dataclass
class Chunk:
    chunk_id: str          # "{page_id}_c{index}"
    page_id: str
    page_title: str
    page_date: str         # ISO date string
    chunk_index: int
    text: str
    token_count: int = 0

    def __post_init__(self) -> None:
        if self.token_count == 0:
            self.token_count = estimate_tokens(self.text)


def _split_by_sentences(text: str) -> List[str]:
    """Split text into sentences, preserving Chinese punctuation."""
    # Split on sentence-ending punctuation followed by whitespace or end
    pattern = r'(?<=[。！？.!?\n])\s*'
    parts = re.split(pattern, text)
    return [p.strip() for p in parts if p.strip()]


def chunk_text(
    text: str,
    page_id: str,
    page_title: str,
    page_date: str,
    target_tokens: int = 700,
    max_tokens: int = 900,
) -> List[Chunk]:
    """
    Chunk a page's full text into Chunk objects.

    Algorithm:
    1. Split by double-newline (natural paragraphs).
    2. Merge consecutive short paragraphs until approaching target_tokens.
    3. If a single paragraph exceeds max_tokens, split by sentences,
       then by characters as last resort.
    """
    if not text or not text.strip():
        return []

    paragraphs = [p.strip() for p in re.split(r'\n{2,}', text) if p.strip()]

    chunks: List[Chunk] = []
    buffer: List[str] = []
    buffer_tokens = 0

    def flush_buffer(buf: List[str], idx: int) -> Chunk:
        joined = "\n\n".join(buf)
        return Chunk(
            chunk_id=f"{page_id}_c{idx}",
            page_id=page_id,
            page_title=page_title,
            page_date=page_date,
            chunk_index=idx,
            text=joined,
        )

    for para in paragraphs:
        para_tokens = estimate_tokens(para)

        if para_tokens > max_tokens:
            # Flush current buffer first
            if buffer:
                chunks.append(flush_buffer(buffer, len(chunks)))
                buffer, buffer_tokens = [], 0

            # Split oversized paragraph by sentences
            sentences = _split_by_sentences(para)
            sent_buf: List[str] = []
            sent_tokens = 0
            for sent in sentences:
                st = estimate_tokens(sent)
                if sent_tokens + st > max_tokens and sent_buf:
                    chunks.append(flush_buffer(sent_buf, len(chunks)))
                    sent_buf, sent_tokens = [], 0
                if st > max_tokens:
                    # Character-level split as last resort
                    for i in range(0, len(sent), int(max_tokens * 2.5)):
                        piece = sent[i: i + int(max_tokens * 2.5)]
                        if piece.strip():
                            chunks.append(Chunk(
                                chunk_id=f"{page_id}_c{len(chunks)}",
                                page_id=page_id,
                                page_title=page_title,
                                page_date=page_date,
                                chunk_index=len(chunks),
                                text=piece.strip(),
                            ))
                else:
                    sent_buf.append(sent)
                    sent_tokens += st
            if sent_buf:
                chunks.append(flush_buffer(sent_buf, len(chunks)))
        else:
            if buffer_tokens + para_tokens > target_tokens and buffer:
                chunks.append(flush_buffer(buffer, len(chunks)))
                buffer, buffer_tokens = [], 0
            buffer.append(para)
            buffer_tokens += para_tokens

    if buffer:
        chunks.append(flush_buffer(buffer, len(chunks)))

    return chunks
