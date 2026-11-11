"""Okapi BM25 relevance scoring functions."""

from __future__ import annotations

import math


def compute_idf(total_docs: int, doc_freq: int) -> float:
    """Compute non-negative Robertson-Sparck Jones IDF: ln(1 + (N - df + 0.5) / (df + 0.5))."""
    if total_docs <= 0 or doc_freq <= 0:
        return 0.0
    numerator = total_docs - doc_freq + 0.5
    denominator = doc_freq + 0.5
    ratio = max(0.0, numerator / denominator)
    return math.log(1.0 + ratio)


def score_bm25(
    tf: int,
    doc_length: int,
    avg_doc_length: float,
    total_docs: int,
    doc_freq: int,
    k1: float = 1.5,
    b: float = 0.75,
) -> float:
    """Compute Okapi BM25 score for a single term or phrase occurrence in a document."""
    if tf <= 0 or total_docs <= 0 or doc_freq <= 0:
        return 0.0
    idf = compute_idf(total_docs, doc_freq)
    if avg_doc_length <= 0.0:
        norm = 1.0
    else:
        norm = 1.0 - b + b * (doc_length / avg_doc_length)
    denom = tf + k1 * norm
    if denom <= 0.0:
        return 0.0
    return idf * ((tf * (k1 + 1.0)) / denom)

