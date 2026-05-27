# EN: Common request and response envelopes for all agents.
# KO: 모든 Agent가 공유하는 요청 및 응답 Envelope 스키마입니다.

from pydantic import BaseModel, Field
from typing import Any, Optional


class AgentRequest(BaseModel):
    project_id: str = Field(..., description="프로젝트 ID")
    documents: list[dict] = Field(default=[], description="RAG 검색 결과 문서 청크")
    context: Optional[dict] = Field(None, description="추가 컨텍스트")


class AgentResponse(BaseModel):
    success: bool = True
    agent_name: str = Field(..., description="수행한 Agent 이름")
    result: Any = Field(None, description="Agent 처리 결과 JSON")
    error: Optional[str] = None
