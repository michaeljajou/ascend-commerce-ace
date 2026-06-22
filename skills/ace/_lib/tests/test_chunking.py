from _lib import chunking


def test_empty_text_returns_no_chunks():
    assert chunking.chunk_text("") == []
    assert chunking.chunk_text("   \n\n  ") == []


def test_short_text_is_single_chunk():
    chunks = chunking.chunk_text("How do I request a sample? Use the #samples channel.")
    assert len(chunks) == 1
    assert "sample" in chunks[0]


def test_paragraphs_group_under_max_chars():
    text = "Para one.\n\nPara two.\n\nPara three."
    chunks = chunking.chunk_text(text, max_chars=1000)
    assert len(chunks) == 1
    assert "Para one." in chunks[0] and "Para three." in chunks[0]


def test_paragraphs_split_when_exceeding_max_chars():
    text = "A" * 100 + "\n\n" + "B" * 100
    chunks = chunking.chunk_text(text, max_chars=120, overlap=0)
    assert len(chunks) == 2


def test_long_paragraph_is_hard_split_with_overlap():
    para = "word " * 200  # ~1000 chars, single paragraph
    chunks = chunking.chunk_text(para, max_chars=300, overlap=50)
    assert len(chunks) >= 3
    assert all(len(c) <= 300 for c in chunks)
