"""
Similarity utilities for deduplication.
Supports:
  - Cosine similarity on embedding vectors (primary)
  - MinHash / SimHash as fast pre-filter (optional)
"""
from __future__ import annotations

import hashlib
from typing import Dict, List, Optional, Tuple

import numpy as np


# ── Cosine similarity ────────────────────────────────────────────────────────

def cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    """Cosine similarity between two 1-D vectors."""
    norm_a = np.linalg.norm(a)
    norm_b = np.linalg.norm(b)
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return float(np.dot(a, b) / (norm_a * norm_b))


def batch_cosine_similarity(
    query: np.ndarray,
    matrix: np.ndarray,
) -> np.ndarray:
    """
    Compute cosine similarity between query vector and each row of matrix.
    Returns 1-D array of similarities.
    """
    norms = np.linalg.norm(matrix, axis=1)
    query_norm = np.linalg.norm(query)
    if query_norm == 0:
        return np.zeros(len(matrix))
    norms = np.where(norms == 0, 1e-10, norms)
    return matrix.dot(query) / (norms * query_norm)


# ── MinHash (datasketch) ──────────────────────────────────────────────────────

_minhash_available = False
try:
    from datasketch import MinHash, MinHashLSH
    _minhash_available = True
except ImportError:
    pass


def build_minhash(text: str, num_perm: int = 128) -> "MinHash | None":
    """Build a MinHash object from text (character 3-grams)."""
    if not _minhash_available:
        return None
    from datasketch import MinHash
    m = MinHash(num_perm=num_perm)
    for i in range(max(1, len(text) - 2)):
        gram = text[i: i + 3].encode("utf-8")
        m.update(gram)
    return m


def minhash_jaccard(m1: "MinHash", m2: "MinHash") -> float:
    """Estimate Jaccard similarity between two MinHash objects."""
    if m1 is None or m2 is None:
        return 0.0
    return m1.jaccard(m2)


# ── SimHash (lightweight, no dependency) ─────────────────────────────────────

def simhash(text: str, bits: int = 64) -> int:
    """
    Compute SimHash fingerprint of text using character 3-grams.
    Returns an integer fingerprint.
    """
    v = [0] * bits
    for i in range(max(1, len(text) - 2)):
        gram = text[i: i + 3].encode("utf-8")
        h = int(hashlib.md5(gram).hexdigest(), 16)
        for j in range(bits):
            if h & (1 << j):
                v[j] += 1
            else:
                v[j] -= 1
    fingerprint = 0
    for j in range(bits):
        if v[j] > 0:
            fingerprint |= 1 << j
    return fingerprint


def simhash_similarity(fp1: int, fp2: int, bits: int = 64) -> float:
    """Estimate similarity from SimHash Hamming distance."""
    xor = fp1 ^ fp2
    hamming = bin(xor).count("1")
    return 1.0 - hamming / bits
