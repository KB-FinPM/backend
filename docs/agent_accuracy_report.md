# Agent Accuracy Report

## 범위

이번 보강은 담당 범위인 Chat Input Agent, Chat Output Agent, Schedule Management Agent와 프론트엔드 채팅 표시 계약을 대상으로 했다.

문서 생성 core agent 내부 로직은 수정하지 않았다.

- `app/agents/core_agents/requirement_agent/`
- `app/agents/core_agents/wbs_agent/`
- `app/agents/core_agents/screen_design_agent/`
- `app/agents/core_agents/unittest_agent/`

## 예시 기반 보정 레이어

이번 작업의 “학습”은 LLM fine-tuning이 아니라 사람이 검수한 예시 기반 intent correction이다.

- seed fixture: `tests/fixtures/agent_accuracy_learning_seed_cases.json`
- curated example index: `app/agents/input_agents/chat_input_agent/intent_examples.json`
- retriever: `app/agents/input_agents/chat_input_agent/intent_example_retriever.py`
- normalizer: `app/agents/input_agents/chat_input_agent/korean_command_normalizer.py`

문서 RAG/vector DB와 사용자 명령 학습 데이터를 섞지 않는다. 예시는 메모리에서 로드하고, char n-gram similarity와 exact/substr boost로 top-k를 계산한다.

예시 보정은 rule 결과를 무조건 덮어쓰지 않는다.

- top score가 threshold 이상이어야 한다.
- top1/top2 margin이 충분해야 한다.
- negative example이 있으면 위험한 false positive를 막는다.
- 낮은 확신이면 실행 대신 clarification으로 남긴다.

## 고정한 케이스

### Chat Input Agent

`tests/fixtures/agent_accuracy_learning_seed_cases.json`의 input case 23개와 기존 `input_agent_commands.json` 골든 케이스를 함께 검증한다.

- 회의록/액션아이템/화면설계서/단위테스트케이스/일정 표현 오타 보정
- 회의록 TODO 추출과 회의록 요약/정리 요청 분리
- 요구사항/구축요건정의서 기반 산출물 생성 분류
- 이번주/다음주 할 일 조회
- TODO 완료/상태 변경 alias
- pending action confirm/cancel 축약어
- 다운로드 요청의 missing slot
- `일정이 뭐야?`, `일정 만들어줘`, `일정표 만들어줘` 구분

### Schedule Management Agent

seed schedule case와 기존 회의록 골든 케이스를 함께 검증한다.

- `해야`, `할일`, `TODO`, `이번주`, `다음주`, `오늘`, `회의록`, `액션아이템` assignee 방지
- `내일까지`, `낼까지`, `이번 주 금요일까지`, `다음 주 월요일까지` 날짜 해석
- `다음 회의 전까지`는 due date를 invent하지 않고 미확정 상태 유지
- `블락`, `막힘`, `보류` 같은 상태 alias
- 중복 TODO 제거와 ambiguous match 처리

### Chat Output Agent

seed output case와 기존 output event 골든 케이스를 함께 검증한다.

- correction notice를 자연어로 표시
- 내부 enum/event 문자열을 사용자 메시지에 노출하지 않음
- clarification command action 유지
- progress/download/result payload 안정성 유지

### Frontend

`frontend/tests/run-node-tests.mjs`에서 backend 응답 계약을 검증한다.

- assistant message가 `corrections`를 보존
- canonical 추천 명령 유지
- download schema 유지
- progress UI의 overall/sub/batch 분리 계약 유지

## 평가 명령

`scripts/evaluate_agent_accuracy.py`는 seed fixture를 직접 실행해 정확도 지표를 출력하고 threshold 미달 시 non-zero로 종료한다.

현재 기준:

- Input intent accuracy: 100%
- Artifact type accuracy: 100%
- Schedule action accuracy: 100%
- Correction accuracy: 100%
- Negative guard accuracy: 100%
- Confirm/cancel accuracy: 100%
- Schedule agent accuracy: 100%
- Output agent accuracy: 100%
- False positive count: 0
- False negative count: 0

## 검증 결과

- `python -m pytest --collect-only`: 437 collected
- `python -m pytest`: 437 passed
- `python scripts/evaluate_agent_accuracy.py`: passed, all metrics 100%
- `npm test`: passed
- `npm run build`: passed

## 남은 한계

- raw user log를 자동 학습하지 않는다. 새 케이스는 사람이 검수한 fixture에 추가한 뒤 테스트와 평가 스크립트를 통과해야 반영한다.
- 문서 생성 core agent의 산출물 품질 평가는 이번 범위 밖이다.
- 실제 Bedrock/S3/AWS 호출은 테스트하지 않았고 local fake/stub 범위에서 검증했다.
- 장문의 회의록에서 복합 문장 분리 정확도는 추가 curated seed case가 필요하다.
