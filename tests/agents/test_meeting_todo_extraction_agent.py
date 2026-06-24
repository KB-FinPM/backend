import pytest

from app.agents.input_agents.meeting_todo_extraction_agent.agent import (
    MeetingTodoExtractionAgent,
)


EXAMPLE_MEETING_NOTES = """
회의명: 내규/외규 및 이슈회의
회의일시: 2025. 1.16(목)
장소: KB신관 13층 13-7
참석자: 임태운 감사역, 강승일 선임팀장, 유경근 수석, 정재영 팀장, 김병원 이사

외규관련
법제처 자료를 RPA를 통해 축적 가능여부 검토예정 (임태운 감사역)

내규관련
내규 데이터를 감사정보시스템으로 이관 필요함
데이터양이 많음 약 400GB

영업감사관련 상세요건 정의 미진 건에 대한 이슈 제기 (유경근 PM)
영업감사관련 상세요건중 미진한 건에 대한 정의를 1월중 완료하기로 하였으나, 영업감사부 담당자 부재로 지연되고 있음
영업감사관련 미진사항을 SI개발팀 파악하고 있는 기준으로 정리하여 배포 예정(01.17(금))으로 빠른 대응 요청
1.22(수) 주간보고시 이슈로 제기 예정

와이즈넷 관련 업무협의
layout 정의를 01.17(금)까지 정리 예정 (김병원이사)
결재문서 및 감사문서 열람율 layout 정의를 01.17(금)까지 정리 예정 (김병원이사)
WiseNet 화면 스크린샷 확인 후 스토리보드와 실제 layout 비교 및 최종 레이아웃 확정 예정

기타 논의
비즈플랫폼에서 대응 개발이 필요
검색 성능 저하 우려

이번 회의에서 도출된 실행항목
| No. | 실행항목 | 담당자 | 기한 |
| | | | |
"""


class FailingLlmService:
    async def invoke(self, *args, **kwargs):
        raise RuntimeError("llm unavailable")


class V26ShapeLlmService:
    async def invoke(self, *args, **kwargs):
        return """
        {
          "items": [
            {
              "title": "법제처 자료 RPA 축적 가능 여부 검토",
              "description": "법제처 자료를 RPA로 축적할 수 있는지 검토한다.",
              "assignee": "임태운 감사역",
              "due_date": null,
              "due_date_text": "미정",
              "status": "진행전",
              "source_sentence": "법제처 자료를 RPA를 통해 축적 가능여부 검토예정 (임태운 감사역)",
              "confidence": 0.92,
              "needs_confirmation": ["기한"]
            }
          ],
          "excluded_candidates": [
            {
              "text": "데이터양이 많음 약 400GB",
              "reason": "현황 설명이며 실행항목이 아니다.",
              "classification": "issue_or_requirement"
            }
          ]
        }
        """


class V27ShapeLlmService:
    async def invoke(self, *args, **kwargs):
        return """
        {
          "items": [
            {
              "title": "법제처 자료 RPA 축적 가능 여부 검토",
              "description": "회의록에서 추출한 TODO입니다.",
              "assignee": "임태운 감사역",
              "due_date": null,
              "due_date_text": "미정",
              "status": "진행전",
              "confidence": "high",
              "source_sentence": "법제처 자료를 RPA를 통해 축적 가능여부 검토예정 (임태운 감사역)",
              "needs_confirmation": ["기한"]
            }
          ],
          "excluded_candidates": [
            {
              "text": "데이터양이 많음 약 400GB",
              "reason": "현황 설명이며 실행항목이 아니다.",
              "classification": "issue"
            },
            {
              "text": "내규 데이터를 감사정보시스템으로 이관 필요함",
              "reason": "요구사항 후보이지만 담당자와 실행 단위가 불명확하다.",
              "classification": "requirement_candidate"
            }
          ]
        }
        """


@pytest.mark.anyio
async def test_meeting_todo_extraction_agent_extracts_body_todos_when_action_table_is_empty() -> None:
    agent = MeetingTodoExtractionAgent(
        llm_service=FailingLlmService(),
        use_llm_by_default=True,
    )

    result = await agent.extract(
        project_id="PRJ-001",
        meeting_notes=EXAMPLE_MEETING_NOTES,
        permission_scope=["project:read"],
        source_document_ids=["DOC-MEETING-001"],
        context={"use_llm": True},
    )

    todos = result["todo_items"]
    todos_by_title = {todo["title"]: todo for todo in todos}

    assert set(todos_by_title) == {
        "법제처 자료 RPA 축적 가능 여부 검토",
        "영업감사 미진사항 정리 및 배포",
        "영업감사 상세요건 미진 이슈 주간보고 제기",
        "WiseNet 연계 layout 정의 정리",
        "결재문서 및 감사문서 열람율 layout 정의",
        "WiseNet 최종 레이아웃 확정",
    }

    assert [section["title"] for section in result["meeting_document"]["sections"]][:3] == [
        "외규관련",
        "내규관련",
        "영업감사관련 상세요건 정의 미진 건에 대한 이슈 제기 (유경근 PM)",
    ]

    rpa = todos_by_title["법제처 자료 RPA 축적 가능 여부 검토"]
    assert rpa["assignee"] == "임태운 감사역"
    assert rpa["due_date"] is None
    assert rpa["status"] == "TODO"
    assert "기한" in rpa["needs_confirmation"]

    distribution = todos_by_title["영업감사 미진사항 정리 및 배포"]
    assert distribution["assignee"] == "SI개발팀"
    assert distribution["due_date"] == "2025-01-17"
    assert distribution["status"] == "TODO"
    assert "근거:" not in distribution["description"]
    assert "회의록" not in distribution["description"]
    assert "영업감사" in distribution["description"]
    assert "배포" in distribution["description"]

    weekly_issue = todos_by_title["영업감사 상세요건 미진 이슈 주간보고 제기"]
    assert weekly_issue["assignee"] == "유경근 PM"
    assert weekly_issue["due_date"] == "2025-01-22"
    assert weekly_issue["status"] == "TODO"
    assert "1.22" in weekly_issue["description"]

    layout = todos_by_title["WiseNet 연계 layout 정의 정리"]
    assert layout["assignee"] == "김병원 이사"
    assert layout["due_date"] == "2025-01-17"
    assert "layout" in layout["description"]
    final_layout = todos_by_title["WiseNet 최종 레이아웃 확정"]
    assert final_layout["assignee"] == "김병원 이사"
    assert final_layout["due_date"] is None
    assert "스크린샷" in final_layout["description"]
    assert not any(
        forbidden in todo["description"]
        for todo in todos
        for forbidden in (
            "회의록에서 추출",
            "회의록 기반",
            "원본 문서에서 추출",
            "근거:",
            "출처:",
            "파일:",
        )
    )
    assert not any(
        "담당자 부재로 지연" in todo["title"] or "비즈플랫폼" in todo["title"]
        for todo in todos
    )

    candidates = result["candidate_items"]
    assert any("비즈플랫폼" in candidate["source_sentence"] for candidate in candidates)
    assert any("검색 성능 저하 우려" in candidate["source_sentence"] for candidate in candidates)
    assert any("담당자 부재로 지연" in candidate["source_sentence"] for candidate in candidates)
    assert any(
        candidate["classification"] == "issue"
        and "데이터양이 많음" in candidate["source_sentence"]
        for candidate in candidates
    )
    assert any(
        candidate["classification"] == "requirement_candidate"
        and "이관 필요함" in candidate["source_sentence"]
        for candidate in candidates
    )
    assert not any("비즈플랫폼" in todo["title"] for todo in todos)
    assert result["metadata"]["fallback_used"] is True
    assert result["metadata"]["llm_used"] is False


@pytest.mark.anyio
async def test_meeting_todo_extraction_agent_marks_unclear_owner_or_due_date_for_confirmation() -> None:
    agent = MeetingTodoExtractionAgent()

    result = await agent.extract(
        project_id="PRJ-001",
        meeting_notes="회의일시: 2025. 1.16(목)\n최종 레이아웃 확정 예정",
    )

    todo = result["todo_items"][0]
    assert todo["status"] == "NEEDS_CONFIRMATION"
    assert "담당자" in todo["needs_confirmation"]
    assert "기한" in todo["needs_confirmation"]
    assert todo["source_sentence"] == "최종 레이아웃 확정 예정"


@pytest.mark.anyio
async def test_meeting_todo_extraction_agent_accepts_v26_llm_json_shape() -> None:
    agent = MeetingTodoExtractionAgent(
        llm_service=V26ShapeLlmService(),
        use_llm_by_default=True,
    )

    result = await agent.extract(
        project_id="PRJ-001",
        meeting_notes=EXAMPLE_MEETING_NOTES,
        context={"use_llm": True},
    )

    assert result["todo_items"][0]["status"] == "TODO"
    assert result["todo_items"][0]["source_type"] == "MEETING_NOTE"
    assert result["candidate_items"][0]["source_sentence"] == "데이터양이 많음 약 400GB"
    assert result["metadata"]["llm_used"] is True


@pytest.mark.anyio
async def test_meeting_todo_extraction_agent_accepts_v27_llm_json_shape() -> None:
    agent = MeetingTodoExtractionAgent(
        llm_service=V27ShapeLlmService(),
        use_llm_by_default=True,
    )

    result = await agent.extract(
        project_id="PRJ-001",
        meeting_notes=EXAMPLE_MEETING_NOTES,
        context={"use_llm": True},
    )

    todo = result["todo_items"][0]
    assert todo["status"] == "TODO"
    assert todo["confidence"] == 0.9
    assert "회의록에서 추출" not in todo["description"]
    assert "RPA" in todo["description"]
    assert [candidate["classification"] for candidate in result["candidate_items"]] == [
        "issue",
        "requirement_candidate",
    ]
