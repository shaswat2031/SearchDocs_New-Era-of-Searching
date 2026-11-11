"""Text normalization and tokenization utilities for SearchCore."""

from __future__ import annotations

import re
import unicodedata
from collections import defaultdict

_TOKEN_RE = re.compile(r"[a-z0-9]+")


def tokenize(text: str) -> list[str]:
    """Normalize and split text into lowercase alphanumeric tokens."""
    if not text:
        return []
    normalized = unicodedata.normalize("NFKC", text).lower()
    return _TOKEN_RE.findall(normalized)


def tokenize_with_positions(text: str, start_pos: int = 0) -> tuple[dict[str, list[int]], int]:
    """Return a mapping of term -> sorted token positions and total token count."""
    tokens = tokenize(text)
    positions: dict[str, list[int]] = defaultdict(list)
    for offset, token in enumerate(tokens):
        positions[token].append(start_pos + offset)
    return dict(positions), len(tokens)


def tokenize_document(title: str, content: str) -> tuple[dict[str, list[int]], int]:
    """Tokenize document title and content with a position gap so phrases do not cross boundaries."""
    title_tokens = tokenize(title)
    content_tokens = tokenize(content)

    positions: dict[str, list[int]] = defaultdict(list)
    for idx, token in enumerate(title_tokens):
        positions[token].append(idx)

    # Leave a 1-slot gap between title and body when both are present.
    content_start = len(title_tokens) + (1 if title_tokens and content_tokens else 0)
    for idx, token in enumerate(content_tokens):
        positions[token].append(content_start + idx)

    total_length = len(title_tokens) + len(content_tokens)
    return dict(positions), total_length

