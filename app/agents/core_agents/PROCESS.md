# Core Agents PROCESS

## 1. 입력 경계

backend에서는 문서 원본, S3 객체, PgVector, Bedrock client를 Core Agent가 직접 다루지 않습니다.

```text
Router
-> Service
-> GenerationOrchestrator
-> ArtifactAgent
-> RequirementAgent / WbsAgent / ScreenDesignAgent
-> ValidatorAgent
```

Core Agent 입력은 `AgentRequest`입니다.

```text
project_id
context
documents: RAG 검색 결과 문서 청크
```

## 2. 요구사항명세서 생성

Requirement Agent는 다음 기준으로 요구사항을 생성합니다.

- 구축요건정의서 또는 RAG 문서 chunk를 근거로 요구사항을 추출합니다.
- Core Agent 내부에서 요구사항 추출 전용 chunk 전처리를 수행합니다. 범용 Input Parser는 수정하지 않습니다.
- 요구사항은 `Biz요건명`, `업무영역`, `domain`, `category` 기준으로 그룹화할 수 있도록 metadata를 구성합니다.
- 구축요건정의서의 3단 표는 1번째 컬럼을 `Biz요건명`, 2번째 컬럼을 `요구사항명`, 3번째 컬럼을 `기능/비기능요구사항`으로 매핑합니다.
- 3단 표의 3번째 컬럼에서 첫 상위 bullet(`o`, `O`, `ㅇ`, `○`)을 만나면 같은 계열 bullet 항목은 `요구사항명`으로 분리하고, 뒤따르는 `-` 등 하위 bullet은 직전 요구사항의 `기능/비기능요구사항`으로 유지합니다.
- 구축요건정의서의 2단 표는 1번째 컬럼을 `Biz요건명`으로 보고, 2번째 컬럼의 상위내용을 `요구사항명`, 들여쓰기/bullet/다른 기호로 시작하는 하위내용을 `기능/비기능요구사항`으로 매핑합니다.
- 단, 2단 표 헤더가 `요구사항명 | 기능/비기능요구사항`인 경우 1번째 컬럼은 첫 `요구사항명`으로 사용하고, 2번째 컬럼 안의 `o`, `O`, `ㅇ` bullet은 추가 `요구사항명`으로 분리합니다. 이때 `-` bullet은 직전 요구사항의 `기능/비기능요구사항`으로 유지합니다.
- 2단/3단 표 위 제목은 `업무`, `구분`으로 매핑합니다.
- `개요`, `범위`, `배경`, `일정`, `조직도`, `별첨` 성격의 섹션과 `주 1)` 형태의 주석은 요구사항 추출 대상에서 제외합니다.
- 인프라 구축 프로젝트에서는 OCP, Kafka, EFK, CDC, API Gateway, Service Mesh, Monitoring, Logging, DB, 보안, 백업 등을 주요 구축 영역으로 봅니다.
- 개발 프로젝트에서는 업무, 화면, 기능, 인터페이스, 데이터, 권한, 배치 등을 주요 영역으로 봅니다.
- 문서에 없는 내용은 추측하지 않습니다.

출력은 backend 최소 스키마를 따릅니다.

```json
{
  "artifact_type": "REQUIREMENT_SPEC",
  "requirements": []
}
```

## 3. WBS 생성

WBS Agent는 요구사항명세서 성격의 입력을 기반으로 WBS를 생성합니다.

현재 backend flow에서는 `documents` 또는 `context.requirement_artifact`를 요구사항 입력으로 사용합니다.

처리 규칙:

```text
1레벨: Biz요건명 / 업무영역
2레벨: 프로젝트 유형별 단계
3레벨: 대표 요구사항별 세부 작업
```

프로젝트 유형별 단계:

```text
infra: 분석, 설계, 개발환경 구축, 스테이징 구축, 운영 구축
development: 분석, 설계, 개발, 테스트, 운영 이행
hybrid: 분석, 설계, 개발/구축, 스테이징 검증, 운영 이행
```

출력은 backend 최소 스키마를 따릅니다.

```json
{
  "artifact_type": "WBS",
  "tasks": []
}
```

## 4. 화면설계서 생성

Screen Design Agent는 요구사항ID 기준으로 화면설계서 페이지를 생성합니다.

처리 규칙:

- 하나의 요구사항ID는 하나의 화면설계 페이지로 매핑합니다.
- `탬플릿_화면설계서.pptx`의 3페이지 템플릿 슬라이드를 복제해 사용합니다.
- Description 영역에는 요구사항명세서의 `기능/비기능요구사항` 내용만 입력합니다.
- Description 영역에 요구사항ID, 요구사항명, 임의 UI 항목명(`검색 조건`, `처리 버튼` 등)을 추가하지 않습니다.
- 작성자는 요청의 `author`, `writer`, `created_by`, `user_id` 순서로 매핑하고, 없으면 `작성자`를 사용합니다.

출력은 backend 최소 스키마를 따릅니다.

```json
{
  "artifact_type": "SCREEN_DESIGN",
  "screens": []
}
```

화면 표시항목은 템플릿 Description 매핑을 위해 `screens[].metadata.display_items`에 `Description` 항목만 보관합니다.

## 5. S3 / PgVector / Bedrock 접근 원칙

Core Agent에서는 다음을 직접 수행하지 않습니다.

```text
boto3.client(...)
bedrock.invoke_model(...)
S3 get_object / put_object
PgVector 직접 query
DB repository 직접 호출
```

필요 시 반드시 `app/orchestrator/generation_orchestrator.py`의 경계를 사용합니다.

```text
GenerationOrchestrator.invoke_agent_llm()
GenerationOrchestrator.search_agent_context()
```

## 6. 검증

Agent 결과는 `ValidatorAgent`를 통해 backend 최소 스키마로 검증됩니다.

- Requirement: `RequirementArtifact`
- WBS: `WbsArtifact`
- Screen Design: `ScreenDesignArtifact`

실패 가능한 상황은 예외를 그대로 노출하지 않고 `AgentResponse(success=False, error="...")`로 반환합니다.

## 7. 산출물 파일 생성 및 후속 입력 문서 사용

생성 API는 Agent JSON 검증 후 다음 후처리를 수행합니다.

```text
Agent JSON 생성
-> ValidatorAgent 검증
-> ArtifactExportService 파일 생성
-> S3_GENERATED_PREFIX 하위 업로드
-> artifacts / artifact_versions 저장
```

산출물별 파일 형식은 다음과 같습니다.

```text
REQUIREMENT_SPEC -> 요구사항명세서.xlsx
WBS -> WBS.xlsx
SCREEN_DESIGN -> 화면설계서.pptx
```

요구사항명세서는 WBS와 화면설계서의 선행 문서가 되어야 하므로, export 후 `documents`에도 `DocumentType.REQUIREMENT_SPEC`으로 등록합니다. 따라서 WBS와 화면설계서는 `/api/generate/requirement` 응답의 `result.exported_document.document_id`를 `source_document_ids`에 넣어 호출합니다.

## S3 템플릿 기반 산출물 생성

1. `/api/generate/requirement`, `/api/generate/wbs`, `/api/generate/screen-design` 호출이 성공하면 Agent 결과 JSON을 생성합니다.
2. `output_mapper.json`을 로딩합니다. S3 모드에서는 `S3_TEMPLATE_PREFIX/output_mapper.json`을 우선 사용합니다.
3. 산출물 유형별 템플릿을 S3에서 다운로드합니다.
   - 요구사항명세서: `S3_TEMPLATE_PREFIX/탬플릿_요구사항명세서.xlsx`
   - WBS: `S3_TEMPLATE_PREFIX/탬플릿_WBS.xlsx`
   - 화면기획서: `S3_TEMPLATE_PREFIX/탬플릿_화면설계서.pptx`
4. 템플릿의 표지/개정이력/데이터 시트/슬라이드 placeholder를 mapper 기준으로 채웁니다.
5. 완성된 파일을 `S3_GENERATED_PREFIX/{project_id}/{artifact_type}/{artifact_id}/` 아래 업로드합니다.

## Requirement extraction process parity
1. `/api/generate/requirement` 호출 시 선택된 `source_document_ids`의 chunk 전체를 조회합니다.
2. Core Agent 내부 전처리로 pipe table 행과 section title을 정규화합니다.
3. 표 기반 요구사항이 있으면 LLM을 거치지 않고 행 단위로 atom을 생성합니다.
4. 표 기반 요구사항이 없으면 각 chunk를 기존 sample_0605의 extraction prompt 형식으로 LLM에 전달합니다.
5. 반환 atom을 통합한 뒤 중복 제거, Biz요건 ID(`Biz-0001`), 요구사항 ID(`REQ-00001`)를 재채번합니다.
6. `output_mapper.json` 및 S3/로컬 템플릿 기준으로 요구사항명세서 Excel에 매핑합니다.
