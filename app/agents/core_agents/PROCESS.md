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
- 요구사항은 `Biz요건명`, `업무영역`, `domain`, `category` 기준으로 그룹화할 수 있도록 metadata를 구성합니다.
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

Screen Design Agent는 화면과 관련 있는 요구사항만 선별합니다.

포함 후보:

```text
화면, UI, UX, 페이지, 조회, 등록, 수정, 삭제, 승인, 결재, 관리, 검색, 대시보드
```

제외 후보:

```text
API 단독, 배치, 인프라, 백업, 서버 구성, Kafka, EFK, CDC, Service Mesh, 모니터링, 로그, 보안 단독 요건
```

출력은 backend 최소 스키마를 따릅니다.

```json
{
  "artifact_type": "SCREEN_DESIGN",
  "screens": []
}
```

화면 표시항목은 `screens[].metadata.display_items`에 보관합니다.

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

요구사항명세서는 WBS와 화면설계서의 선행 문서가 되어야 하므로, export 후 `documents`에도 `DocumentType.REQUIREMENT_SPEC`으로 등록합니다. 따라서 WBS와 화면설계서는 `/generate/requirement` 응답의 `result.exported_document.document_id`를 `source_document_ids`에 넣어 호출합니다.

## S3 템플릿 기반 산출물 생성

1. `/generate/requirement`, `/generate/wbs`, `/generate/screen-design` 호출이 성공하면 Agent 결과 JSON을 생성합니다.
2. `output_mapper.json`을 로딩합니다. S3 모드에서는 `S3_TEMPLATE_PREFIX/output_mapper.json`을 우선 사용합니다.
3. 산출물 유형별 템플릿을 S3에서 다운로드합니다.
   - 요구사항명세서: `S3_TEMPLATE_PREFIX/탬플릿_요구사항명세서.xlsx`
   - WBS: `S3_TEMPLATE_PREFIX/탬플릿_WBS.xlsx`
   - 화면기획서: `S3_TEMPLATE_PREFIX/탬플릿_화면설계서.pptx`
4. 템플릿의 표지/개정이력/데이터 시트/슬라이드 placeholder를 mapper 기준으로 채웁니다.
5. 완성된 파일을 `S3_GENERATED_PREFIX/{project_id}/{artifact_type}/{artifact_id}/` 아래 업로드합니다.

## Requirement extraction process parity
1. `/generate/requirement` 호출 시 선택된 `source_document_ids`의 chunk 전체를 조회합니다.
2. 각 chunk를 기존 sample_0605의 extraction prompt 형식으로 LLM에 전달합니다.
3. LLM은 chunk당 최대 10개의 요구사항 atom JSON 배열을 반환합니다.
4. 반환 atom을 통합한 뒤 중복 제거, Biz요건 ID, 요구사항 ID를 재채번합니다.
5. `output_mapper.json` 및 S3/로컬 템플릿 기준으로 요구사항명세서 Excel에 매핑합니다.
