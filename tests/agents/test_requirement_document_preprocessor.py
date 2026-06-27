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


def test_requirement_document_preprocessor_preserves_document_order() -> None:
    documents = [
        {
            "document_id": "DOC-MEET-001",
            "chunk_index": "2",
            "section_title": "회의록 A",
            "text": "첫 번째 회의록 후반 내용",
        },
        {
            "document_id": "DOC-REQ-001",
            "chunk_index": "0",
            "section_title": "요구사항",
            "text": "구축요건정의서 첫 번째 내용",
        },
        {
            "document_id": "DOC-MEET-001",
            "chunk_index": "3",
            "section_title": "",
            "text": "회의록 A 후속 내용",
        },
    ]

    normalized = normalize_requirement_documents(documents)

    assert [item["document_id"] for item in normalized] == [
        "DOC-REQ-001",
        "DOC-MEET-001",
        "DOC-MEET-001",
    ]
    assert normalized[2]["section_title"] == "회의록 A"


def test_requirement_document_preprocessor_prioritizes_construction_before_meeting_notes() -> None:
    documents = [
        {
            "document_id": "DOC-MEET-001",
            "chunk_index": "0",
            "section_title": "회의록 A",
            "text": "회의록 내용",
            "metadata": {"document_type": "MEETING_NOTES"},
        },
        {
            "document_id": "DOC-REQ-001",
            "chunk_index": "1",
            "section_title": "구축요건정의서 A",
            "text": "구축요건 내용 1",
            "metadata": {"document_type": "CONSTRUCTION_REQUIREMENT_DEFINITION"},
        },
        {
            "document_id": "DOC-REQ-001",
            "chunk_index": "2",
            "section_title": "구축요건정의서 A",
            "text": "구축요건 내용 2",
            "metadata": {"document_type": "CONSTRUCTION_REQUIREMENT_DEFINITION"},
        },
    ]

    normalized = normalize_requirement_documents(documents)

    assert [item["document_id"] for item in normalized] == [
        "DOC-REQ-001",
        "DOC-REQ-001",
        "DOC-MEET-001",
    ]


def test_requirement_document_preprocessor_splits_meeting_notes_into_candidates() -> None:
    documents = [
        {
            "document_id": "DOC-MEET-001",
            "chunk_id": "CHUNK-001",
            "section_title": "회의록",
            "text": (
                "회의명 | 기술협상회의\n"
                "회의 주제 | 업무 내용중 추가 필요한 부분 협의\n"
                "1. 환율 고시 및 조회 | - 실시간 환율 채집 및 고시 관리 기능 필요 | - Pricing 기능 필요 | "
                "- 채집 및 고시된 환율을 직원이 기간별로 조회할 수 있는 화면 구현\n"
                "1-1. 실시간 환율 채집 및 고시 관리 기능 상세 | - 시장 LP 및 CMBS로부터의 시장 환율을 채집 및 고시 | "
                "- 시장 채집 불가한 환율 및 Swap PT의 경우 수기 입력 기능 구현\n"
            ),
            "metadata": {
                "document_type": "MEETING_NOTES",
                "source_file_name": "시연용_회의록.v.1.docx",
            },
        }
    ]

    normalized = normalize_requirement_documents(documents)

    assert len(normalized) >= 4
    texts = [item["text"] for item in normalized]
    assert any("실시간 환율 채집 및 고시 관리 기능 필요" in text for text in texts)
    assert any("Pricing 기능 필요" in text for text in texts)
    assert any(text.startswith("환율 고시 및 조회") for text in texts)
    assert all(
        "회의명" not in text
        and "회의 주제" not in text
        for text in texts
    )
