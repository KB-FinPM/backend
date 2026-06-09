# EN: Tests for requirement-agent document pre-processing.
# KO: 요구사항 Agent 문서 전처리 테스트입니다.

from app.agents.core_agents.requirement_agent.document_preprocessor import (
    normalize_requirement_documents,
)


def test_requirement_document_preprocessor_normalizes_pipe_rows_and_bad_index() -> None:
    documents = [
        {
            "chunk_index": "not-a-number",
            "section_title": "상세요건",
            "text": "회원 |  회원 조회  |  목록을 조회한다.\n\n",
        },
        {
            "chunk_index": "2",
            "section_title": "",
            "text": "권한 |권한 관리|권한 변경 기능을 제공한다.",
        },
    ]

    normalized = normalize_requirement_documents(documents)

    assert normalized[0]["text"] == "회원 | 회원 조회 | 목록을 조회한다."
    assert normalized[1]["section_title"] == "상세요건"
    assert normalized[1]["text"] == "권한 | 권한 관리 | 권한 변경 기능을 제공한다."
