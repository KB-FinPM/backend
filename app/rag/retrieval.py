from app.core.logger import get_logger
from typing import Any

logger = get_logger(__name__)


class RetrievalService:
    """
    Vector 검색 전담 서비스.
    항상 project_id와 permission scope를 포함해서 검색합니다.
    """

    async def search(self, project_id: str, query: str, top_k: int = 5) -> list[dict]:
        logger.info(f"[RAG] search | project_id={project_id} | query={query[:50]}")

        # TODO: ChromaDB 또는 pgvector 검색 구현
        # 반드시 project_id 필터 포함

        return []  # Mock


retrieval_service = RetrievalService()
