<!-- EN: Backend project overview and local development guide. -->
<!-- KO: 백엔드 프로젝트 개요와 로컬 개발 가이드 문서입니다. -->

# PM-Agent

Local setup, run, and test instructions are maintained in
[docs/DEVELOPMENT_GUIDE.md](docs/DEVELOPMENT_GUIDE.md).

AI 기반 프로젝트 관리(PM) 지원 플랫폼

---

# 1. 프로젝트 개요

PM-Agent는 RFP, 회의록 등의 프로젝트 문서를 기반으로 요구사항 정의서, 일정, Action Item 등을 생성하는 AI 기반 PM 지원 플랫폼입니다.

해커톤 MVP 기준 목표는 다음과 같습니다.

```text
- PDF 기반 요구사항 자동 생성
- 회의록 기반 Action Item 추출
- RAG 기반 문맥 검색
- Agent 기반 AI 구조 설계
```

---

# 2. 전체 시스템 구조

```text
Frontend (React.js)
    ↓
CloudFront (AWS)
    ↓
S3 Static Hosting (AWS)

Frontend API Call
    ↓
EC2 (AWS)
 ├── FastAPI (API 서버)
 ├── Orchestrator
 ├── Agents
 ├── RAG
 └── Storage
    ↓
Amazon Bedrock
    ↓
S3 / SQLite / ChromaDB
```

---

# 3. 기술 스택

## Frontend

```text
- React.js
- TypeScript(javascript)
- Vite
- Axios
```

## Backend

```text
- Python 3.11
- FastAPI
- LangChain
- Uvicorn
```

## AI / LLM

```text
- Amazon Bedrock
- Claude Sonnet
```

## Storage

```text
- AWS S3
- SQLite (초기 MVP)
- ChromaDB (Vector Store)
```

## Infra

```text
- EC2
- CloudFront
- S3 Static Hosting
- GitHub Actions (선택)
```

---

# 4. 개발 환경

## Python 버전

반드시 아래 버전을 사용합니다.

```text
Python 3.11.x
```

확인 방법:

```bash
python --version
```

---

# 5. 프로젝트 구조

```text
pm-agent/

├── app/
│   ├── api/
│   ├── orchestrator/
│   ├── agents/
│   ├── schemas/
│   ├── storage/
│   ├── rag/
│   └── core/
│
├── tests/
├── prompts/
├── requirements.txt
├── README.md
└── run.sh
```

---

# 6. 디렉토리 설명

## app/api/

FastAPI Router 영역입니다.

역할:

```text
- HTTP 요청 처리
- Request 검증
- Orchestrator 호출
- Response 반환
```

예시:

```text
POST /generate/requirement
POST /upload
GET /health
```

주의:

```text
API Layer에서는 직접 Bedrock 호출 금지
```

예시 구조:

```text
api/
 ├── generation.py
 ├── upload.py
 └── health.py
```

---

## app/orchestrator/

전체 흐름 제어 영역입니다.

역할:

```text
- Agent 호출 순서 관리
- RAG 검색 수행
- Validator 호출
- 결과 후처리
```

예시 흐름:

```text
1. 문서 조회
2. Vector 검색
3. RequirementAgent 호출
4. Validator 호출
5. 결과 반환
```

예시 구조:

```text
orchestrator/
 ├── generation_orchestrator.py
 ├── schedule_orchestrator.py
 └── impact_orchestrator.py
```

예시 코드:

```python
class GenerationOrchestrator:

    async def generate_requirement(self, request):

        docs = retrieval_service.search(...)

        result = requirement_agent.generate(docs)

        validated = validator_agent.validate(result)

        return validated
```

핵심:

```text
Orchestrator는 비즈니스 흐름만 제어한다.
```

---

## app/agents/

실제 AI 기능 수행 영역입니다.

역할:

```text
- 요구사항 생성
- 일정 추출
- Validator
- 영향 분석
```

예시 구조:

```text
agents/
 ├── requirement_agent/
 │    └── agent.py
 │
 ├── validator_agent/
 │    └── agent.py
 │
 └── schedule_agent/
      └── agent.py
```

예시 코드:

```python
class RequirementAgent:

    def generate(self, documents):

        prompt = ...

        result = llm.invoke(prompt)

        return result
```

핵심 원칙:

```text
Agent는 하나의 역할만 수행한다.
```

금지 사항:

```text
- FastAPI Router 직접 처리
- DB 직접 저장
- HTTP Response 생성
```

---

## app/schemas/

공통 데이터 구조 정의 영역입니다.

역할:

```text
- Request Schema
- Response Schema
- Agent 입출력 구조
```

예시:

```python
class AgentRequest(BaseModel):
    project_id: str
    documents: list
```

중요:

```text
모든 Agent는 공통 Schema를 준수해야 함
```

예시 구조:

```text
schemas/
 ├── request.py
 ├── response.py
 └── agent.py
```

---

## app/storage/

저장소 접근 영역입니다.

역할:

```text
- S3 업로드
- DB 저장
- 파일 조회
```

예시 구조:

```text
storage/
 ├── s3.py
 ├── sqlite.py
 └── repository.py
```

주의:

```text
Agent 내부에서 직접 boto3 사용 금지
```

좋은 구조:

```python
s3_service.upload(...)
```

---

## app/rag/

RAG 전용 로직 영역입니다.

역할:

```text
- Chunking
- Embedding
- Vector Search
- Retriever
```

예시 구조:

```text
rag/
 ├── chunking.py
 ├── embedding.py
 ├── retrieval.py
 └── vectorstore.py
```

예시 흐름:

```text
PDF
→ chunking
→ embedding
→ vector 저장
```

검색 시:

```text
query
→ vector similarity search
```

핵심:

```text
RAG는 LLM에 넣을 문맥을 준비하는 영역이다.
```

---

## app/core/

공통 인프라 영역입니다.

역할:

```text
- Config 관리
- Logger
- Bedrock Wrapper
- 공통 Utility
```

예시 구조:

```text
core/
 ├── config.py
 ├── logger.py
 ├── llm.py
 └── constants.py
```

예시:

```python
class LLMService:

    def invoke(self, prompt):
        ...
```

핵심:

```text
모든 Agent가 공통 방식으로 LLM을 사용하도록 관리한다.
```

---

## tests/

테스트 코드 영역입니다.

역할:

```text
- 단위 테스트
- Agent 테스트
```

예시 구조:

```text
tests/
 ├── test_requirement_agent.py
 └── test_validator.py
```

---

## prompts/

Prompt 관리 영역입니다.

역할:

```text
- Prompt Template 관리
- Agent Prompt 분리
```

예시 구조:

```text
prompts/
 ├── requirement_prompt.txt
 └── validator_prompt.txt
```

주의:

```text
Prompt를 코드 내부에 직접 하드코딩하지 않는다.
```

---

# 7. 브랜치 전략

## Main Branch

```text
main
```

운영 가능한 코드만 merge합니다.

---

## Feature Branch

각 Agent는 Feature Branch 기준으로 개발합니다.

예시:

```text
feature/requirement-agent
feature/validator-agent
feature/schedule-agent
```

---

# 8. 개발 환경 세팅

## 1. Repository Clone

```bash
git clone <repository-url>
```

---

## 2. Virtual Environment 생성

### Mac / Linux

```bash
python -m venv venv
source venv/bin/activate
```

### Windows

```bash
python -m venv venv
venv\Scripts\activate
```

---

## 3. 패키지 설치

```bash
pip install -r requirements.txt
```

---

# 9. 실행 방법

## FastAPI 실행

```bash
sh run.sh
```

또는:

```bash
uvicorn app.main:app --reload
```

---

# 10. Agent 개발 가이드

## Agent 개발 원칙

### 1. Agent는 하나의 역할만 수행

좋은 예:

```text
RequirementAgent
→ 요구사항 생성만 담당
```

나쁜 예:

```text
RequirementAgent 안에서:
- DB 저장
- API Response 생성
- 파일 업로드
```

---

### 2. Agent는 공통 Schema 사용

입력:

```python
AgentRequest
```

출력:

```python
AgentResponse
```

---

### 3. Bedrock 직접 호출 금지

반드시:

```python
core/llm.py
```

를 통해 호출합니다.

---

# 11. 패키지 관리 정책

## 중요 원칙

```text
requirements.txt 중앙 관리
```

---

## 패키지 추가 시

반드시 팀 공유 후 반영합니다.

---

## 권장 패키지

```text
fastapi
langchain
boto3
pydantic
chromadb
```

---

## 금지 패키지

해커톤 MVP에서는 아래 패키지 사용을 지양합니다.

```text
- tensorflow
- torch
- transformers
```

이유:

```text
- 용량 증가
- 설치 시간 증가
- 충돌 위험 증가
```

---

# 12. 공통 실행 정책

## Logger 사용

모든 Agent는 Logger를 사용합니다.

예시:

```python
logger.info("Requirement generation started")
```

---

## print 사용 지양

```text
print() 대신 logger 사용
```

---

# 13. 배포 구조 (MVP 기준)

## Frontend

```text
npm Build
→ S3 업로드
→ CloudFront 제공
```

---

## Backend

```text
Git Pull
→ EC2
→ FastAPI 실행
```

---

## AI

```text
FastAPI
→ Bedrock Claude 호출
```

---

# 14. GitHub Actions 배포 흐름 (선택)

## Frontend

```text
GitHub Push
→ GitHub Actions
→ npm build
→ S3 sync
→ CloudFront 반영
```

---

## Backend

```text
GitHub Push
→ GitHub Actions
→ EC2 SSH 접속
→ git pull
→ FastAPI restart
```

---

# 15. 핵심 개발 원칙

```text
1. Agent는 역할별로 분리한다.
2. Orchestrator가 흐름을 관리한다.
3. 공통 Schema를 반드시 준수한다.
4. 패키지 버전은 중앙 관리한다.
5. API Layer는 얇게 유지한다.
6. Agent 내부에서 DB/S3 직접 접근 금지.
7. Prompt와 로직을 분리한다.
8. MVP에서는 단순함을 우선한다.
```

---

# 16. 최종 MVP 목표

현재 MVP 목표는 다음 흐름을 안정적으로 구현하는 것입니다.

```text
PDF 업로드
→ RAG 검색
→ Requirement Agent 실행
→ Validator
→ 결과 반환
```

---

# 17. 팀 역할 권장 구조

## Infra + Backend + Orchestrator

```text
- FastAPI 구조 관리
- requirements 관리
- 공통 Schema 관리
- Orchestrator 구현
- 배포 및 실행 환경 관리
```

---

## Agent 담당자

```text
- RequirementAgent 구현
- ValidatorAgent 구현
- ScheduleAgent 구현
- Prompt 개선
- 결과 품질 개선
```

---

# 18. 핵심 설계 철학

```text
Frontend
→ 요청

API Layer
→ 요청 전달

Orchestrator
→ 흐름 제어

Agents
→ AI 기능 수행

RAG
→ 문맥 검색

Storage
→ 저장소 접근
```

핵심은:

```text
"LLM 중심 구조"가 아니라
"Orchestrator 중심 구조"
```

라는 점입니다.

LLM은 전체 시스템의 일부 도구이며,
실제 품질과 안정성은 다음 영역에서 결정됩니다.

```text
- Orchestrator
- 공통 Schema
- RAG 품질
- Validator
- Prompt 관리
```

---

# 19. 해커톤 운영 원칙

해커톤에서는:

```text
완벽한 운영 인프라
```

보다:

```text
빠른 수정
안정적인 실행
설득력 있는 데모
```

가 더 중요합니다.

따라서 MVP 기준에서는:

```text
- 단순한 구조
- 최소 AWS 서비스
- 빠른 개발 속도
```

를 우선합니다.

---

# 20. 권장 AWS 구성 (MVP)

## 필수

```text
- S3
- CloudFront
- EC2
- Bedrock
```

---

## 선택

```text
- RDS
- GitHub Actions
```

---

## MVP 단계에서 제외 가능

```text
- EKS
- ECS
- Lambda
- EventBridge
- SQS
- Neptune
- OpenSearch
- API Gateway
```

이유:

```text
해커톤에서는 운영 복잡도를 줄이고
AI 기능 구현에 집중하기 위함
```

