import numpy as np
import pytest

from src.notion.blocks_to_text import blocks_to_text
from src.pipeline.step6_dedupe import find_duplicates
from src.utils.similarity import cosine_similarity, simhash, simhash_similarity
from src.utils.text_chunker import chunk_text
from src.utils.token_estimator import estimate_tokens


def _chunk(cid, page, date, text="t"):
    return {"chunk_id": cid, "page_id": page, "page_title": page, "page_date": date, "text": text}


def _normed(rows):
    m = np.asarray(rows, dtype=np.float32)
    return m / np.linalg.norm(m, axis=1, keepdims=True)


class TestFindDuplicates:
    def test_earlier_page_is_canonical(self):
        chunks = [_chunk("b_c0", "b", "2024-05-01"), _chunk("a_c0", "a", "2023-01-01")]
        dups = find_duplicates(chunks, [0, 0], _normed([[1, 0], [1, 0.01]]), 0.9)
        assert len(dups) == 1
        assert dups[0]["canonical_page_id"] == "a"
        assert dups[0]["dup_page_id"] == "b"

    def test_same_page_never_paired(self):
        chunks = [_chunk("a_c0", "a", "2024-01-01"), _chunk("a_c1", "a", "2024-01-01")]
        assert find_duplicates(chunks, [0, 0], _normed([[1, 0], [1, 0]]), 0.9) == []

    def test_cross_cluster_flag(self):
        chunks = [_chunk("a_c0", "a", "2024-01-01"), _chunk("b_c0", "b", "2024-02-01")]
        normed = _normed([[1, 0], [1, 0]])
        assert find_duplicates(chunks, [0, 1], normed, 0.9) == []
        assert len(find_duplicates(chunks, [0, 1], normed, 0.9, cross_cluster=True)) == 1

    def test_every_row_checked_across_batches(self):
        # The old cross-cluster loop only examined every 500th chunk.
        n = 7
        chunks = [_chunk(f"p{i}_c0", f"p{i}", f"2024-01-{i + 1:02d}") for i in range(n)]
        rows = [[1, 0, 0]] * 3 + [[0, 1, 0]] * 4
        dups = find_duplicates(chunks, list(range(n)), _normed(rows), 0.99, cross_cluster=True, batch_size=2)
        assert len(dups) == 3 + 6  # C(3,2) + C(4,2)
        assert len({(d["dup_chunk_id"], d["canonical_chunk_id"]) for d in dups}) == len(dups)

    def test_sorted_by_similarity(self):
        chunks = [_chunk(c, c, "2024-01-01") for c in "abc"]
        dups = find_duplicates(chunks, [0, 0, 0], _normed([[1, 0], [1, 0.05], [1, 0.3]]), 0.9)
        sims = [d["similarity"] for d in dups]
        assert sims == sorted(sims, reverse=True)


class TestChunker:
    def test_empty_text(self):
        assert chunk_text("   ", "p", "t", "2024-01-01") == []

    def test_short_paragraphs_merge(self):
        chunks = chunk_text("一\n\n二\n\n三", "p", "t", "2024-01-01")
        assert len(chunks) == 1
        assert chunks[0].chunk_id == "p_c0"

    def test_oversized_cjk_sentence_respects_max_tokens(self):
        text = "情" * 3000  # no sentence punctuation, forces the character fallback
        chunks = chunk_text(text, "p", "t", "2024-01-01", target_tokens=100, max_tokens=150)
        assert len(chunks) > 1
        assert "".join(c.text for c in chunks) == text
        assert all(c.token_count <= 150 * 1.1 for c in chunks)
        assert [c.chunk_index for c in chunks] == list(range(len(chunks)))

    def test_estimate_tokens_positive(self):
        assert estimate_tokens("hello world") >= 1


class TestBlocksToText:
    def test_notion_hosted_file_url_dropped(self):
        blocks = [{
            "type": "image",
            "image": {"type": "file", "file": {"url": "https://prod-files-secure.s3.amazonaws.com/x?X-Amz-Signature=abc"}, "caption": []},
        }]
        assert blocks_to_text(blocks, fetch_children=False) == "[image]"

    def test_external_url_and_caption_kept(self):
        blocks = [
            {"type": "image", "image": {"type": "external", "external": {"url": "https://example.com/a.png"}, "caption": []}},
            {"type": "pdf", "pdf": {"type": "file", "file": {"url": "https://s3/x"}, "caption": [{"plain_text": "合同"}]}},
        ]
        assert blocks_to_text(blocks, fetch_children=False) == "[image: https://example.com/a.png]\n[pdf: 合同]"

    def test_common_blocks(self):
        blocks = [
            {"type": "heading_2", "heading_2": {"rich_text": [{"plain_text": "标题"}]}},
            {"type": "to_do", "to_do": {"rich_text": [{"plain_text": "做"}], "checked": True}},
            {"type": "paragraph", "paragraph": {"rich_text": []}},
        ]
        assert blocks_to_text(blocks, fetch_children=False) == "## 标题\n[x] 做"


class TestSimilarity:
    def test_cosine(self):
        assert cosine_similarity(np.array([1.0, 0]), np.array([2.0, 0])) == pytest.approx(1.0)
        assert cosine_similarity(np.array([0.0, 0]), np.array([1.0, 0])) == 0.0

    def test_simhash_identical(self):
        assert simhash_similarity(simhash("同样的文字内容"), simhash("同样的文字内容")) == 1.0
