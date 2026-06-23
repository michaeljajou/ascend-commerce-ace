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
