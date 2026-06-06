# Core Agents CHANGELOG

## 2026-06-06 sample_0605 통합

### 적용 기준

- `sample_0605.zip`의 `CHANGELOG.md`, `PROCESS.md`, `agents/*/AGENT.md` 기준을 backend Agent 계약에 맞게 반영했습니다.
- backend의 `README.md`, `app/agents/AGENT_DEVELOPMENT.md` 기준을 우선 적용했습니다.
- Core Agent는 `AgentRequest`를 입력받고 `AgentResponse`를 반환하며, FastAPI Response, DB, S3, PgVector, Bedrock client를 직접 사용하지 않습니다.

### 변경 파일

```text
app/agents/core_agents/requirement_agent/agent.py
app/agents/core_agents/wbs_agent/agent.py
app/agents/core_agents/screen_design_agent/agent.py
app/agents/core_agents/CHANGELOG.md
app/agents/core_agents/PROCESS.md
app/orchestrator/generation_orchestrator.py
util/agent_generation_utils.py
```

### 주요 변경 내용

- Requirement Agent
  - 구축요건정의서 분석 기준을 `Biz요건명 / 업무영역` 중심으로 확장했습니다.
  - 인프라, 개발, 하이브리드 프로젝트 유형을 고려하도록 프롬프트와 fallback 생성 규칙을 반영했습니다.
  - LLM 호출이 필요한 경우 `GenerationOrchestrator.invoke_agent_llm()`을 통해서만 호출하도록 변경했습니다.

- WBS Agent
  - placeholder 구현을 제거하고 요구사항 기반 WBS 생성 로직을 추가했습니다.
  - `Biz요건명` 기준 1레벨 그룹을 만들고 프로젝트 유형별 단계명을 적용합니다.
  - 인프라 프로젝트는 `분석 / 설계 / 개발환경 구축 / 스테이징 구축 / 운영 구축` 관점으로 생성합니다.
  - 개발 프로젝트는 `분석 / 설계 / 개발 / 테스트 / 운영 이행` 관점으로 생성합니다.
  - 하이브리드 프로젝트는 `분석 / 설계 / 개발/구축 / 스테이징 검증 / 운영 이행` 관점으로 생성합니다.

- Screen Design Agent
  - placeholder 구현을 제거하고 화면 관련 요구사항만 선별해 화면 설계 JSON을 생성합니다.
  - API, 배치, 인프라, 백업, 서버 구성처럼 화면과 직접 관련이 낮은 항목은 제외합니다.
  - 화면별 표시항목은 `metadata.display_items`에 최대 7개 수준으로 구성합니다.

- Orchestrator Boundary
  - `GenerationOrchestrator.invoke_agent_llm()`을 추가해 core agent가 Bedrock/client 계층을 직접 접근하지 않도록 했습니다.
  - `GenerationOrchestrator.search_agent_context()`를 추가해 향후 core agent가 추가 RAG 검색이 필요할 때도 orchestrator 경계를 거치도록 했습니다.

- Shared Utility
  - 공통 JSON 파싱, 요구사항 atom 정규화, 프로젝트 유형 분류, WBS phase 결정, 화면 관련 요구사항 판별 로직을 `util/agent_generation_utils.py`로 분리했습니다.

### 의존성

- 이번 backend 통합본에서는 신규 외부 라이브러리를 추가하지 않았습니다.
- sample의 `python-docx`, `openpyxl`, `python-pptx`, `pgvector`, `sentence-transformers`는 standalone 산출물 파일 생성/로컬 벡터 저장용 성격이 강해 backend core agent JSON 계약에는 직접 필요하지 않습니다.

## 2026-06-06 산출물 파일 Export 연동

- `/generate/requirement` 성공 시 요구사항명세서 `.xlsx` 파일을 생성하고 `S3_GENERATED_PREFIX` 하위로 업로드하도록 연결했습니다.
- 요구사항명세서 생성 결과는 `DocumentType.REQUIREMENT_SPEC` 문서로도 등록하여 WBS/화면설계서의 입력 문서로 사용할 수 있게 했습니다.
- `/generate/wbs` 성공 시 WBS `.xlsx` 파일을 생성하고 S3에 업로드하도록 연결했습니다.
- `/generate/screen-design` 성공 시 화면설계서 `.pptx` 파일을 생성하고 S3에 업로드하도록 연결했습니다.
- 생성 API 응답에 `exported_file.storage_path`와, 요구사항명세서의 경우 `exported_document.document_id`를 포함하도록 변경했습니다.

## S3 Template Export Fix

- 요구사항명세서, WBS, 화면기획서 파일 생성 시 S3 `S3_TEMPLATE_PREFIX` 아래 템플릿을 우선 사용하도록 수정했습니다.
- S3 템플릿 다운로드 실패 시 `app/agents/core_agents/template` 내 포함 템플릿으로 fallback합니다.
- Mac 한글 파일명 NFC/NFD 차이를 고려해 S3 prefix 목록에서 정규화된 파일명 매칭을 지원합니다.
- `output_mapper.json`의 `template_path`, `placeholder_sheets`, `data_sheet`, `description_table` 설정을 실제 Excel/PPTX 작성 로직에 반영했습니다.

## 2026-06-06 - Requirement extraction parity fix
- 기존 sample_0605의 chunk 단위 요구사항 atom 추출 방식을 RequirementAgent에 재반영했습니다.
- 생성 요청 문구를 RAG 검색어로 사용하지 않고 선택 문서의 전체 chunk를 로딩하도록 변경했습니다.
- 요구사항 ID/Biz요건 ID를 기존 샘플과 동일한 `REQ-0001`, `BIZ-001` 형식으로 재채번합니다.
- 중복 요구사항 제거 기준을 기존 샘플의 category/Biz요건명/요구사항명/요구사항유형/설명 기준으로 맞췄습니다.

## 2026-06-06 requirement atomic split restore

- sample_0605의 요구사항 atom 분리 방식에 맞춰 `기능구분 | 주요내용 | 상세` 형태의 구축요건정의서 표를 행/상세 단위로 분해하도록 보강했습니다.
- 표 상세 셀에 여러 bullet/하위 요구사항이 포함된 경우 하나의 요구사항으로 뭉치지 않고 atom 단위로 분리합니다.
- 요구사항명세서 템플릿의 데이터 영역 병합 셀을 해제한 뒤 행을 기록하도록 수정하여, 여러 요구사항이 빈 행으로 출력되는 현상을 방지했습니다.
