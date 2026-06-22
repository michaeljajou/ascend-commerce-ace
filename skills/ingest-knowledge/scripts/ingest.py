#!/usr/bin/env python3
"""Ingest a brand's knowledge into the active profile's store.

Deterministic, no reasoning: load documents → chunk → embed → upsert. Runs on a 24h cron
(blueprint) and on demand via `/ace update`. The agent does not "think" here — it just runs this.

Usage:
    python ingest.py --source <drive-folder-id|local-path> [--kind auto|local|drive]

Exposes `run_ingest(conn, source, embedder, kind)` so tests can drive it with a fake embedder
and an in-memory DB.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Make the shared _lib importable whether run by Hermes (code execution) or pytest.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))  # → skills

from _lib import chunking, drive, store  # noqa: E402
from _lib.embeddings import Embedder, get_embedder  # noqa: E402
from _lib.models import Chunk  # noqa: E402


def run_ingest(
    conn,
    source: str,
    embedder: Embedder,
    *,
    kind: str = "auto",
    max_chars: int = chunking.DEFAULT_MAX_CHARS,
    overlap: int = chunking.DEFAULT_OVERLAP,
) -> dict:
    """Ingest all documents from ``source`` into ``conn``. Returns a summary dict.

    Idempotent per document: re-running replaces a document's chunks rather than duplicating.
    """
    docs = drive.load_documents(source, kind=kind)
    total_chunks = 0
    for doc in docs:
        texts = chunking.chunk_text(doc.text, max_chars=max_chars, overlap=overlap)
        if not texts:
            continue
        vectors = embedder(texts)
        store.upsert_document(conn, doc.id, doc.title, path=doc.path, updated_at=doc.updated_at)
        store.replace_chunks(
            conn,
            doc.id,
            [Chunk(document_id=doc.id, ord=i, text=t, embedding=v) for i, (t, v) in enumerate(zip(texts, vectors))],
        )
        total_chunks += len(texts)
    return {"documents": len(docs), "chunks": total_chunks}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Ingest brand knowledge into the profile store.")
    ap.add_argument("--source", required=True, help="Drive folder id or local path")
    ap.add_argument("--kind", default="auto", choices=["auto", "local", "drive"])
    args = ap.parse_args(argv)

    conn = store.connect()
    summary = run_ingest(conn, args.source, get_embedder(), kind=args.kind)
    print(json.dumps(summary))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
