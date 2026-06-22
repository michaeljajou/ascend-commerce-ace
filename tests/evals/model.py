"""Chat-model abstraction for the LLM-judged eval harness.

A `Model` is any callable ``list[messages] -> str`` (messages are OpenAI-style dicts). The runtime
model calls OpenRouter; tests inject deterministic fakes. `extract_json` robustly pulls the JSON
verdict out of a model reply (handles code fences / surrounding prose).
"""

from __future__ import annotations

import json
import os
from typing import Callable

Model = Callable[[list[dict]], str]

DEFAULT_EVAL_MODEL = "anthropic/claude-sonnet-4-6"
DEFAULT_JUDGE_MODEL = "anthropic/claude-sonnet-4-6"
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"


def openrouter_model(
    model: str | None = None, api_key: str | None = None, temperature: float = 0.0
) -> Model:
    """Build a Model backed by OpenRouter chat completions (deterministic by default)."""
    model = model or os.environ.get("ACE_EVAL_MODEL", DEFAULT_EVAL_MODEL)
    api_key = api_key or os.environ.get("OPENROUTER_API_KEY")

    def call(messages: list[dict]) -> str:
        import httpx  # lazy: harness imports without httpx when only using fakes

        if not api_key:
            raise RuntimeError("OPENROUTER_API_KEY is not set")
        resp = httpx.post(
            OPENROUTER_URL,
            headers={"Authorization": f"Bearer {api_key}"},
            json={"model": model, "messages": messages, "temperature": temperature},
            timeout=120.0,
        )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"]

    return call


def extract_json(text: str) -> dict:
    """Best-effort extraction of the first balanced JSON object in ``text``.

    Tolerates ```json fences and leading/trailing prose. Raises ValueError if none parses.
    """
    if not text:
        raise ValueError("empty model response")
    # Fast path: whole string is JSON.
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    # Scan for the first balanced {...}.
    depth = 0
    start = -1
    in_str = False
    esc = False
    for i, ch in enumerate(text):
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == "{":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0 and start >= 0:
                candidate = text[start : i + 1]
                try:
                    return json.loads(candidate)
                except json.JSONDecodeError:
                    start = -1
    raise ValueError(f"no JSON object found in model response: {text[:200]!r}")
