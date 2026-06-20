# Agent Accuracy Report

## 범위

이번 보강은 담당 범위인 Chat Input Agent, Chat Output Agent, Schedule Management Agent와 프론트엔드 채팅/추천 유틸 계약을 대상으로 했다.

문서 생성 core agent 내부 로직은 수정하지 않았다.

- `app/agents/core_agents/requirement_agent/`
- `app/agents/core_agents/wbs_agent/`
- `app/agents/core_agents/screen_design_agent/`
- `app/agents/core_agents/unittest_agent/`

## 고정한 골든 케이스

### Chat Input Agent

`tests/fixtures/input_agent_commands.json` 기준 16개 한국어 명령을 고정했다.

- 요구사항/요구사항저의서/WBS/일정표/화면설계/UI 설계/테스트케이스 생성 요청
- 회의록 기반 액션아이템 추출
- 이번 주 할 일 조회
- TODO 상태 변경
- PM 산출물 개념 질문
- 모호한 문서/일정 생성 요청의 clarification
- 다운로드 요청의 누락 슬롯
- 확인/취소 워크플로우

### Chat Output Agent

`tests/fixtures/output_agent_events.json` 기준 12개 이벤트를 고정했다.

- 확인 요청, 액션 시작/완료/실패
- clarification/required info/general QA
- 일정 조회 및 TODO 완료
- 다운로드 준비/다운로드 필수 정보/알 수 없는 이벤트
- `generation_progress.sub_progress`와 `batch_progress` 보존
- 다운로드 파일의 `artifact_type`, `content_type`, `download_url` 안정 스키마
- malformed progress payload 무시

### Schedule Management Agent

`tests/fixtures/schedule_meeting_notes.json` 기준 5개 회의록 케이스를 고정했다.

- 명시 담당자와 월/일 마감일
- 콜론 담당자와 이번 주 금요일
- `다음 회의 전까지` 같은 미확정 마감
- 담당자 미정 placeholder
- 동일 회의록 내 중복 TODO 제거

### Frontend Utility Contract

`frontend/tests/run-node-tests.mjs`에 다음 회귀 테스트를 추가했다.

- Chat Output Agent의 확장 다운로드 스키마 보존
- 기본 추천 명령이 깨진 문자열이 아닌 실제 한국어 PM 명령인지 확인

## 구현 메모

- Input Agent는 실제 한국어 동의어와 오타를 보강하되, 회의록 요약 요청과 TODO 추출 요청을 분리했다.
- Output Agent는 결과 payload의 download/progress 필드를 프론트가 그대로 사용할 수 있도록 안전하게 정규화한다.
- Schedule Management Agent는 한국어 회의록에서 담당자/마감일/상태/중복을 더 엄격하게 처리한다.
- Frontend는 추천 명령과 fallback 응답 문구의 인코딩 문제를 정리했고, 확장 download file payload를 보존한다.

## 남은 한계

- core 문서 생성 Agent의 산출물 품질 평가는 이번 범위 밖이다.
- 실제 Bedrock/S3/AWS 호출은 테스트하지 않았고 모두 local fake/stub 범위에서 검증했다.
- 장문의 회의록에서 복합 문장 분리 정확도는 추가 실사용 로그 기반 골든 케이스가 필요하다.
- 기존 코드 일부에는 과거 인코딩 깨짐 문자열이 남아 있을 수 있어, 사용자 노출 문자열은 후속 pass에서 계속 정리하는 것이 좋다.
