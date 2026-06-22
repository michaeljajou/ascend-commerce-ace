"""Embedding providers.

`get_embedder()` returns the runtime embedder (OpenRouter over HTTP). Tests inject a
deterministic fake instead, so nothing here is imported during unit tests unless explicitly
requested — and `httpx` is imported lazily so the module loads on the stdlib alone.

An Embedder is any callable: ``list[str] -> list[list[float]]``.
"""

from __future__ import annotations

import hashlib
import math
import os
from typing import Callable, Protocol

Embedder = Callable[[list[str]], list[list[float]]]


class _EmbedderProto(Protocol):  # documentation of the contract
    def __call__(self, texts: list[str]) -> list[list[float]]: ...


# --- runtime: OpenRouter ---------------------------------------------------------------------

DEFAULT_MODEL = "openai/text-embedding-3-small"
OPENROUTER_URL = "https://openrouter.ai/api/v1/embeddings"


def openrouter_embedder(
    model: str | None = None, api_key: str | None = None
) -> Embedder:
    """Build an embedder that calls OpenRouter's embeddings endpoint.

    Reads ``OPENROUTER_API_KEY`` and ``ACE_EMBED_MODEL`` from the environment unless overridden.
    """
    model = model or os.environ.get("ACE_EMBED_MODEL", DEFAULT_MODEL)
    api_key = api_key or os.environ.get("OPENROUTER_API_KEY")

    def embed(texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        import httpx  # lazy: keeps stdlib-only import path clean

        if not api_key:
            raise RuntimeError("OPENROUTER_API_KEY is not set")
        resp = httpx.post(
            OPENROUTER_URL,
            headers={"Authorization": f"Bearer {api_key}"},
            json={"model": model, "input": texts},
            timeout=60.0,
        )
        resp.raise_for_status()
        data = resp.json()["data"]
        return [row["embedding"] for row in data]

    return embed


def get_embedder() -> Embedder:
    """Default runtime embedder. Override in tests by passing a fake explicitly."""
    return openrouter_embedder()


# --- testing: deterministic fake -------------------------------------------------------------


def hashing_embedder(dim: int = 1024) -> Embedder:
    """A deterministic, offline embedder for tests.

    Hashes tokens into a fixed-dim bag-of-words vector and L2-normalizes. Texts that share
    vocabulary get high cosine similarity, so retrieval relevance is meaningfully testable
    without any network or model.
    """

    def embed(texts: list[str]) -> list[list[float]]:
        out: list[list[float]] = []
        for t in texts:
            vec = [0.0] * dim
            for tok in _tokens(t):
                h = int(hashlib.md5(tok.encode()).hexdigest(), 16)
                vec[h % dim] += 1.0
            norm = math.sqrt(sum(x * x for x in vec))
            out.append([x / norm for x in vec] if norm else vec)
        return out

    return embed


# Filtered so the fake embedder reflects *content* overlap, not shared filler words —
# making it a faithful offline proxy for a real embedding model.
_STOPWORDS = frozenset(
    """a an the and or but is are was were be been being to of in on at for with my your you i
    we they it this that these those do does did how what when where why who which can could would
    should will shall may might if then than as so no not yes me us them he she his her their our""".split()
)


def _tokens(text: str) -> list[str]:
    words = "".join(c.lower() if c.isalnum() else " " for c in text).split()
    return [w for w in words if w and w not in _STOPWORDS]
