# Core Agents Process

이 문서는 `app/agents/core_agents` 하위 Core Agent들이 현재 어떤 순서와 기준으로 산출물을 생성하는지 정리한 문서입니다.

## 1. 전체 흐름

1. 사용자가 산출물 생성을 요청한다.
2. `GenerationService`가 요청한 산출물 타입과 소스 문서를 검증한다.
3. `GenerationOrchestrator`가 문서를 검색하고, 각 Core Agent에 필요한 컨텍스트를 전달한다.
4. Core Agent는 입력 문서와 기존 산출물 컨텍스트를 바탕으로 JSON 결과를 생성한다.
5. `ArtifactExportService`가 JSON을 Excel 또는 PPTX로 변환하고 S3에 업로드한다.
6. 필요하면 생성된 요구사항명세서가 다시 문서로 등록되어 후속 WBS, 화면설계서, 단위테스트계획서 생성의 입력으로 사용된다.

## 2. 공통 원칙

- Core Agent는 S3, DB, Bedrock 클라이언트를 직접 다루지 않는다.
- 실제 LLM 호출은 `GenerationOrchestrator.invoke_agent_llm()` 경유로 수행한다.
- 가능한 경우 구조화된 표, 기존 산출물, source metadata를 우선 활용한다.
- JSON 외의 설명 문장은 반환하지 않는다.
- 산출물 생성 시 원문에 없는 내용은 추측하지 않는다. 다만 화면/테스트/WBS처럼 결과물 특성상 필요한 범위는 현재 문맥을 바탕으로 구체화한다.

## 3. 요구사항명세서 생성

### 3.1 입력

- 구축요건정의서 원문
- 표 형태의 요구사항 후보
- 문서 메타데이터

### 3.2 처리 방식

`RequirementAgent`는 다음 순서로 동작한다.

1. 문서를 `normalize_requirement_documents()`로 정규화한다.
2. 표 기반 요구사항을 먼저 추출한다.
3. 표에서 뽑은 후보는 행 단위로 다시 LLM 보정한다.
4. 표가 없거나 충분하지 않으면 chunk 단위 추출로 fallback 한다.
5. 중복을 정리하고 요구사항 ID를 부여한다.
6. 요구사항명세서용 artifact로 변환한다.

### 3.3 현재 특징

- 요구사항 설명은 단순 요약이 아니라 목적, 처리 방식, 운영/제약 포인트를 포함하도록 보정한다.
- 표가 있는 경우 문서 전체를 한 번에 밀어넣지 않고, 행 단위로 조금 더 정확하게 다듬는다.
- `source_doc`, `source_file_name`, `source_document_id`가 유지되도록 처리한다.
- 이 값은 export 시 요구사항명세서의 `근기문서` 또는 `근거문서` 컬럼을 채우는 데 사용된다.

### 3.4 출력

- `artifact_type: REQUIREMENT_SPEC`
- `requirements[]`
- 각 요구사항에는 다음과 같은 메타 정보가 포함될 수 있다.
  - `category`
  - `biz_requirement_id`
  - `biz_requirement_name`
  - `requirement_id`
  - `requirement_name`
  - `requirement_type`
  - `domain`
  - `feature`
  - `description`
  - `note`
  - `source_document_id`
  - `source_doc`

## 4. WBS 생성

### 4.1 입력

- 요구사항명세서
- 구축요건정의서 문맥
- WBS 템플릿의 공통 행
- 산출물 목록 템플릿

### 4.2 처리 방식

`WbsAgent`는 공통 WBS 뼈대를 기준으로 시작한 뒤, 요구사항 문맥을 반영해 개발영역 상세를 구성한다.

1. 템플릿의 공통 WBS 행을 읽는다.
2. 개발영역의 level 1, level 2 구조는 고정으로 유지한다.
3. level 3 이하 상세 작업은 요구사항 digest와 산출물 목록을 참고해 생성한다.
4. 각 phase는 요구사항정의, 분석, 설계, 구현, 테스트, 이행, 안정화 순서로 일정이 나뉜다.
5. 상세 task에는 요구사항 ID와 산출물이 연결된다.

### 4.3 기간 처리

- WBS 기간은 요청 파라미터의 임의 입력값보다 구축요건정의서와 소스 문서에서 분석한 기간을 우선 사용한다.
- `project_period`, `project_duration`, `duration`, `period`, `contract_period` 같은 문구를 문서에서 탐색한다.
- 문서에 기간이 분리되어 적혀 있어도 하나의 문자열로 합쳐서 해석한다.
- 기간이 확인되지 않으면 기본값으로 처리될 수 있다.

### 4.4 현재 특징

- 개발 단계의 일정은 전체 프로젝트 기간을 phase 비율로 나눠 자동 산정한다.
- 단위테스트, 통합테스트, 인수테스트, 이행 관련 항목은 후반부 일정에 맞춰 정렬된다.
- 인프라/특수 WBS는 별도 규칙으로 보정된다.
- `deliverable`은 `template` 폴더의 산출물 목록과 매핑 로직을 참고해 채운다.

### 4.5 출력

- `artifact_type: WBS`
- `development_tasks[]`
- 각 task는 `phase`, `name`, `description`, `source_requirement_ids`, `deliverable`, `metadata`를 가진다.

## 5. 화면설계서 생성

### 5.1 입력

- 요구사항명세서
- 구축요건정의서 문맥
- 화면 관련 요구사항 ID

### 5.2 처리 방식

`ScreenDesignAgent`는 요구사항별 화면 후보를 생성하고, 필요하면 LLM을 사용해 배치 단위로 확장한다.

1. 요구사항 atom을 정규화한다.
2. 같은 요구사항 ID는 중복 제거한다.
3. LLM이 가능하면 화면 목록을 생성한다.
4. 입력이 많을 경우 8개 단위로 잘라서 배치 생성한다.
5. LLM 결과가 불완전하면 deterministic fallback으로 보완한다.
6. 화면별 description과 표시항목을 보정한다.

### 5.3 현재 특징

- `description`은 단순히 요구사항 문장을 복붙하지 않고, 화면 흐름과 사용자의 확인 포인트가 드러나도록 확장한다.
- `display_items`는 화면에 실제 노출될 항목을 최소 3개 이상 갖도록 보정한다.
- 화면 기획서 PPT 생성 시 description table은 템플릿의 `description_table` 설정을 따른다.
- 표의 행 수는 템플릿 설정과 화면 내용에 따라 동적으로 채워진다.

### 5.4 출력

- `artifact_type: SCREEN_DESIGN`
- `screens[]`
- 각 screen은 `screen_id`, `name`, `description`, `source_requirement_ids`, `metadata.display_items`를 가진다.

## 6. 단위테스트계획서 생성

### 6.1 입력

- 요구사항명세서
- 화면설계서
- 화면별 description 및 표시항목

### 6.2 처리 방식

`UnitTestAgent`는 요구사항만 보는 것이 아니라 화면 컨텍스트까지 함께 반영해서 테스트케이스를 만든다.

1. 요구사항 항목을 수집한다.
2. 화면 산출물이 있으면 requirement ID 기준으로 매칭한다.
3. LLM이 가능하면 요구사항별 테스트케이스를 생성한다.
4. LLM 결과가 비어 있으면 scenario spec 기반 fallback을 수행한다.
5. 요구사항별로 정상, 조회, 저장, 수정, 삭제, 권한, 경계, 예외 케이스를 분리한다.

### 6.3 현재 특징

- 테스트케이스 개수를 인위적으로 적게 제한하지 않는다.
- 요구사항과 화면 문맥이 있으면 관련 시나리오를 더 세분화한다.
- `screen_hint`가 있으면 `test_content`에 화면명, 필수 항목 검증, 권한 확인, 결과 반영 점검이 포함된다.
- `scenario_id`는 요구사항과 시나리오를 함께 식별할 수 있도록 구성한다.

### 6.4 출력

- `artifact_type: UNITTEST_SPEC`
- `test_cases[]`
- 각 test case는 `test_case_id`, `test_case_name`, `requirement_id`, `requirement_name`, `scenario_id`, `test_content`, `metadata`를 가진다.

## 7. export 및 템플릿 처리

### 7.1 ArtifactExportService

- 요구사항명세서, WBS, 화면설계서, 단위테스트계획서를 각각 Excel/PPTX로 변환한다.
- 요구사항명세서는 생성 후 문서로 다시 등록한다.
- 이때 생성된 문서 ID는 후속 산출물의 source 문서로 사용할 수 있다.

### 7.2 output_mapper.json

- 템플릿 파일 경로, placeholder sheet, data sheet, description table 설정을 정의한다.
- 화면 설명 테이블은 `display_items`와 설명 내용을 가능한 범위까지 그대로 반영한다.

## 8. 주요 설정 포인트

- `app/core/llm.py`
  - LLM 호출 기본 토큰 수를 관리한다.
- `app/agents/core_agents/template/output_mapper.json`
  - 엑셀/PPTX 템플릿과 매핑 필드를 관리한다.
- `app/agents/core_agents/requirement_agent/agent.py`
  - 구축요건정의서에서 요구사항명세서로 변환하는 핵심 로직이 있다.
- `app/agents/core_agents/screen_design_agent/agent.py`
  - 화면 설명 보정, display_items 최소 개수 보장, 배치 생성이 있다.
- `app/agents/core_agents/wbs_agent/agent.py`
  - 프로젝트 기간 추출과 WBS 일정 분배 로직이 있다.
- `app/agents/core_agents/unit_test_agent/agent.py`
  - 테스트 시나리오 확장과 화면 기반 점검 내용 보정 로직이 있다.

## 9. 확인 기준

- 요구사항명세서의 `근기문서`가 비어 있지 않아야 한다.
- 화면설계서의 `description`이 너무 짧게 한 줄로만 끝나지 않아야 한다.
- 단위테스트계획서의 점검 내용이 단일 문장만 나오지 않아야 한다.
- WBS는 요청 입력값보다 구축요건정의서/소스 문서에서 분석한 기간을 우선해야 한다.
