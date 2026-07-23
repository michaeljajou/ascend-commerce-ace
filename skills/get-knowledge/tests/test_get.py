import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import get  # noqa: E402

KB = {
    "commission": {"rate": "20%", "schedule": "Monthly on the 15th"},
    "faq": [
        {"q": "How do I request a sample?", "a": "Post your address in #samples.", "tags": ["sample"]},
    ],
}


def test_query_returns_relevant_subset():
    out = get.run(KB, query="how do I request a sample")
    assert "sample" in out.lower()


def test_query_off_topic_returns_empty():
    assert get.run(KB, query="weather forecast today") == ""  # never-fabricate signal


def test_section_and_whole():
    assert "20%" in get.run(KB, section="commission")
    assert get.run(KB, section="missing") == ""
    assert "commission" in get.run(KB)  # whole doc


def test_main_without_pyyaml_prints_raw_knowledge(tmp_path, monkeypatch, capsys):
    """The agent's sandbox has no PyYAML. QA 2026-07-23: the sweep agent's one grounding
    call died on `import yaml`; it spent its whole iteration budget hunting the file by
    hand and dropped a creator's question one call short of the reply. Raw text is still
    grounding — and an empty result here would be the WRONG signal (false escalate)."""
    import builtins

    real_import = builtins.__import__

    def no_yaml(name, *a, **k):
        if name == "yaml" or name.startswith("yaml."):
            raise ImportError("No module named 'yaml'")
        return real_import(name, *a, **k)

    monkeypatch.setattr(builtins, "__import__", no_yaml)
    monkeypatch.delitem(sys.modules, "yaml", raising=False)
    kb_file = tmp_path / "knowledge.yaml"
    kb_file.write_text("brand:\n  name: Glow Labs\nfaq:\n  - q: how do i start\n", encoding="utf-8")

    rc = get.main(["--query", "how do I start", "--path", str(kb_file)])

    out = capsys.readouterr().out
    assert rc == 0
    assert "Glow Labs" in out and "how do i start" in out   # whole raw doc, not empty
