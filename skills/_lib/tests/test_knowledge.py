from _lib import knowledge

KB = {
    "brand": {"name": "Pilot Brand", "voice": "Friendly and concise"},
    "commission": {"rate": "20%", "schedule": "Monthly on the 15th", "method": "PayPal on file"},
    "samples": {"how_to_request": "Post your shipping address in #samples", "shipping_time": "5-7 business days"},
    "faq": [
        {"q": "How do I request a sample?", "a": "Post your address in #samples; ships in 5-7 days.",
         "tags": ["sample", "shipping"]},
        {"q": "How do I get started?", "a": "Introduce yourself in #community-chat and join a campaign.",
         "tags": ["getting", "started", "onboarding"]},
    ],
}


def test_find_matches_faq():
    sub = knowledge.find(KB, "how do I request a sample")
    assert "faq" in sub and any("sample" in e["q"].lower() for e in sub["faq"])


def test_find_matches_section_by_keyword():
    sub = knowledge.find(KB, "what is the commission rate")
    assert "commission" in sub


def test_find_empty_on_no_match():
    assert knowledge.find(KB, "what is the weather forecast today") == {}


def test_validate_ok_and_missing():
    assert knowledge.validate(KB) == []
    problems = knowledge.validate({"faq": "not-a-list"})
    assert any("brand" in p for p in problems)
    assert any("faq" in p for p in problems)


def test_run_get_modes():
    assert "commission" in knowledge.run_get(KB)                       # whole
    assert "commission" in knowledge.run_get(KB, section="commission")  # one section
    assert knowledge.run_get(KB, section="nope") == ""                  # missing section
    assert knowledge.run_get(KB, query="weather forecast") == ""        # no match → empty
    assert "sample" in knowledge.run_get(KB, query="request a sample").lower()


def test_load_knowledge_yaml(tmp_path):
    p = tmp_path / "knowledge.yaml"
    p.write_text("brand:\n  name: Acme\nfaq:\n  - q: Hi?\n    a: Hello.\n", encoding="utf-8")
    kb = knowledge.load_knowledge(p)
    assert kb["brand"]["name"] == "Acme"
    assert kb["faq"][0]["a"] == "Hello."


def test_load_knowledge_json(tmp_path):
    p = tmp_path / "knowledge.json"
    p.write_text('{"brand": {"name": "Acme"}, "faq": []}', encoding="utf-8")
    assert knowledge.load_knowledge(p)["brand"]["name"] == "Acme"
