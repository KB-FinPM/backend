# EN: Tests for text chunking helpers.
# KO: 텍스트 chunking 유틸리티 테스트입니다.

from app.rag.chunking import split_text_into_chunks


def test_split_text_into_chunks_returns_indexed_chunks() -> None:
    text = "TITLE:\n" + "A requirement sentence. " * 120

    chunks = split_text_into_chunks(text, max_chars=200, overlap_chars=20)

    assert len(chunks) > 1
    assert chunks[0].chunk_index == 0
    assert chunks[0].section_title == "TITLE"
    assert all(chunk.text for chunk in chunks)


def test_split_text_into_chunks_returns_empty_for_blank_text() -> None:
    assert split_text_into_chunks(" \n ") == []
