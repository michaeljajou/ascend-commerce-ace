"""Deterministic, dependency-free text chunking for ingestion.

Splits a document into overlapping, paragraph-aware chunks sized for embedding + retrieval.
Pure stdlib so it is unit-testable without any installs.
"""

from __future__ import annotations

import re

# Defaults tuned for FAQ/brief-style brand docs: small enough that top-k stays cheap,
# large enough to keep a Q&A pair together.
DEFAULT_MAX_CHARS = 1200
DEFAULT_OVERLAP = 150

_PARA_SPLIT = re.compile(r"\n\s*\n")
_WS = re.compile(r"[ \t]+")


def _normalize(text: str) -> str:
    # Collapse runs of spaces/tabs but preserve paragraph breaks.
    lines = [_WS.sub(" ", ln).strip() for ln in text.splitlines()]
    return "\n".join(lines).strip()


def chunk_text(
    text: str,
    max_chars: int = DEFAULT_MAX_CHARS,
    overlap: int = DEFAULT_OVERLAP,
) -> list[str]:
    """Return a list of chunk strings.

    Groups whole paragraphs up to ``max_chars``; paragraphs longer than ``max_chars`` are
    hard-split with ``overlap`` carried between pieces so context isn't lost at the seam.
    """
    if max_chars <= 0:
        raise ValueError("max_chars must be positive")
    overlap = max(0, min(overlap, max_chars - 1))

    text = _normalize(text)
    if not text:
        return []

    paragraphs = [p.strip() for p in _PARA_SPLIT.split(text) if p.strip()]
    chunks: list[str] = []
    buf = ""

    def flush() -> None:
        nonlocal buf
        if buf.strip():
            chunks.append(buf.strip())
        buf = ""

    for para in paragraphs:
        if len(para) > max_chars:
            flush()
            chunks.extend(_hard_split(para, max_chars, overlap))
            continue
        if not buf:
            buf = para
        elif len(buf) + 2 + len(para) <= max_chars:
            buf = f"{buf}\n\n{para}"
        else:
            flush()
            buf = para
    flush()
    return chunks


def _hard_split(s: str, max_chars: int, overlap: int) -> list[str]:
    pieces: list[str] = []
    start = 0
    step = max_chars - overlap
    while start < len(s):
        pieces.append(s[start : start + max_chars].strip())
        start += step
    return [p for p in pieces if p]
