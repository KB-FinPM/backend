# EN: Retrieval service boundary for project-scoped vector search.
# KO: 프로젝트 범위 검색을 담당하는 Retrieval 서비스 경계입니다.

from app.rag.embedding import EmbeddingService, embedding_service
from app.core.logger import get_logger
from app.repositories.document_repository import DocumentRepository

logger = get_logger(__name__)


class RetrievalService:
    """
    Retrieves project-scoped context chunks for generation.

    Vector search is the default path. When a PostgreSQL pgvector backend is
    available, it is used directly; otherwise the repository falls back to
    in-process ranking with the same embedding contract.
    """

    def __init__(
        self,
        document_repository: DocumentRepository | None = None,
        embedding_service: EmbeddingService | None = None,
    ) -> None:
        self.document_repository = document_repository
        self.embedding_service = embedding_service

    async def search(
        self,
        project_id: str,
        permission_scope: list[str],
        query: str,
        top_k: int | None = None,
        document_ids: list[str] | None = None,
        search_mode: str = "vector",
    ) -> list[dict]:
        logger.info(
            "[RAG] search | "
            f"project_id={project_id} | "
            f"permission_scope={permission_scope} | "
            f"query={query[:50]} | "
            f"document_ids={document_ids or []}"
        )

        if "project:read" not in permission_scope:
            return []

        if self.document_repository is None:
            return []

        query_embedding = None
        if search_mode in {"auto", "vector"} and self.embedding_service is not None:
            try:
                query_embedding = await self.embedding_service.embed_text(query)
            except Exception as exc:
                logger.warning(
                    "[RAG] embedding failed, continuing with text search | "
                    f"project_id={project_id} | error={exc}"
                )

        chunks = await self.document_repository.search_chunks_by_project(
            project_id=project_id,
            query=query,
            limit=top_k,
            document_ids=document_ids,
            query_embedding=query_embedding,
            search_mode=search_mode,
        )
        if not chunks and query:
            chunks = await self.document_repository.search_chunks_by_project(
                project_id=project_id,
                query="",
                limit=top_k,
                document_ids=document_ids,
                query_embedding=None,
                search_mode=search_mode,
            )
        return [
            {
                "chunk_id": chunk.chunk_id,
                "project_id": chunk.project_id,
                "document_id": chunk.document_id,
                "chunk_index": chunk.chunk_index,
                "text": chunk.text,
                "section_title": chunk.section_title,
                "metadata": chunk.chunk_metadata or {},
            }
            for chunk in chunks
        ]


retrieval_service = RetrievalService(embedding_service=embedding_service)
