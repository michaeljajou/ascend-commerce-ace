"""Per-brand knowledge: a single structured YAML file the agent reads directly.

Replaces the old Drive → chunk → embed → vector-search pipeline. At ~10 brands with small,
structured knowledge (brief, FAQ, commission, samples, compliance, campaigns), the model does the
matching far better than keyword/vector retrieval — so we just hand it the relevant YAML.

The knowledge file lives in the brand's profile data dir (per-tenant config, not the repo),
maintained by the operator/brand team. `find()` returns the subset relevant to a query (for token
economy and the offline eval gate); `to_text()` renders YAML for grounding context.

YAML is the authored format (parsed with PyYAML); `.json` is accepted as a fallback.
"""

from __future__ import annotations

import json
from pathlib import Path

from . import store

KNOWLEDGE_FILENAMES = ("knowledge.yaml", "knowledge.yml", "knowledge.json")

# Filler words ignored when matching a query to knowledge content.
_STOPWORDS = frozenset(
    """a an the and or but is are was were be been being to of in on at for with my your you i we
    they it this that these those do does did how what when where why who which can could would
    should will if then than as so no not yes me us them please""".split()
)


def knowledge_path(explicit: str | Path | None = None) -> Path:
    """Resolve the brand's knowledge file (first existing of the known names in the data dir)."""
    if explicit:
        return Path(explicit)
    d = store.data_dir()
    for name in KNOWLEDGE_FILENAMES:
        p = d / name
        if p.exists():
            return p
    return d / "knowledge.yaml"  # default target


def load_knowledge(path: str | Path | None = None) -> dict:
    p = Path(knowledge_path(path))
    text = p.read_text(encoding="utf-8")
    if p.suffix in (".yaml", ".yml"):
        import yaml  # lazy

        return yaml.safe_load(text) or {}
    return json.loads(text or "{}")


def validate(kb: dict, required: tuple[str, ...] = ("brand", "faq")) -> list[str]:
    """Return a list of problems (empty == valid). Used by setup-brand to sanity-check a brand file."""
    problems = []
    if not isinstance(kb, dict):
        return ["knowledge root must be a mapping/object"]
    for key in required:
        if key not in kb:
            problems.append(f"missing required section: {key!r}")
    faq = kb.get("faq")
    if faq is not None and not isinstance(faq, list):
        problems.append("'faq' must be a list of {q, a} entries")
    return problems


def to_text(obj) -> str:
    """Render knowledge (or a subset) compactly for the model to ground on."""
    try:
        import yaml

        return yaml.safe_dump(obj, sort_keys=False, allow_unicode=True).strip()
    except Exception:
        return json.dumps(obj, indent=2, ensure_ascii=False)


def _tokens(s) -> list[str]:
    words = "".join(c.lower() if c.isalnum() else " " for c in str(s)).split()
    return [w for w in words if w and w not in _STOPWORDS]


def find(kb: dict, query: str) -> dict:
    """Return the subset of ``kb`` relevant to ``query`` — matching FAQ entries plus any top-level
    sections whose key/content overlaps the query. Returns ``{}`` when nothing matches (the
    never-fabricate signal: the answer skill must escalate rather than invent).
    """
    qtokens = set(_tokens(query))
    if not qtokens:
        return {}

    result: dict = {}

    matched_faq = []
    for entry in kb.get("faq", []) or []:
        hay = set(_tokens(entry.get("q", "")) + _tokens(entry.get("a", "")))
        for tag in entry.get("tags", []) or []:
            hay.update(_tokens(tag))
        if qtokens & hay:
            matched_faq.append(entry)
    if matched_faq:
        result["faq"] = matched_faq

    for key, val in kb.items():
        if key == "faq":
            continue
        hay = set(_tokens(key)) | set(_tokens(val if isinstance(val, str) else to_text(val)))
        if qtokens & hay:
            result[key] = val

    return result


def run_get(kb: dict, query: str | None = None, section: str | None = None) -> str:
    """Render what the get-knowledge skill returns: relevant subset (query), one section, or all."""
    if query:
        sub = find(kb, query)
        return to_text(sub) if sub else ""
    if section:
        val = kb.get(section)
        return to_text({section: val}) if val is not None else ""
    return to_text(kb)
