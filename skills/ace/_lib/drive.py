"""Google Drive source for brand knowledge.

Two loaders share one shape — ``load_documents(source) -> list[LoadedDoc]`` — so ingestion is
identical whether reading a live Drive folder or a local directory of fixtures in tests.

`httpx`/google client imports are lazy; this module loads on the stdlib alone.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

# Text-like files we ingest as-is. (Google Docs export → text is handled in the Drive loader.)
TEXT_SUFFIXES = {".txt", ".md", ".markdown"}


@dataclass
class LoadedDoc:
    """A single source document ready for chunking."""

    id: str  # stable id (Drive file id, or relative path for local)
    title: str
    text: str
    updated_at: str | None = None
    path: str | None = None


def load_local(folder: str | Path) -> list[LoadedDoc]:
    """Load text/markdown files from a local folder. Used by tests and dev runs."""
    root = Path(folder)
    docs: list[LoadedDoc] = []
    for p in sorted(root.rglob("*")):
        if p.is_file() and p.suffix.lower() in TEXT_SUFFIXES:
            rel = str(p.relative_to(root))
            docs.append(
                LoadedDoc(
                    id=rel,
                    title=p.stem,
                    text=p.read_text(encoding="utf-8", errors="replace"),
                    updated_at=str(int(p.stat().st_mtime)),
                    path=rel,
                )
            )
    return docs


def load_drive(folder_id: str, credentials_path: str | None = None) -> list[LoadedDoc]:
    """Load a brand's Google Drive folder (live runtime path).

    Implemented in Phase 1 against the Google Drive API; exports Google Docs to text/markdown
    and reads plain text/markdown directly. Kept import-light so the module stays stdlib-only
    until actually invoked.
    """
    raise NotImplementedError(
        "load_drive is wired up in Phase 1 ingestion against the Google Drive API; "
        "tests and dev use load_local()."
    )


def load_documents(source: str, *, kind: str = "auto") -> list[LoadedDoc]:
    """Dispatch to the right loader.

    kind: 'local' | 'drive' | 'auto' (auto → local if ``source`` is an existing path else drive).
    """
    if kind == "local" or (kind == "auto" and Path(source).exists()):
        return load_local(source)
    return load_drive(source)
