# EN: Retrieval service boundary for project-scoped vector search.
# KO: 프로젝트 범위 검색을 담당하는 Retrieval 서비스 경계입니다.

from app.core.logger import get_logger
from app.repositories.document_repository import DocumentRepository

logger = get_logger(__name__)


class RetrievalService:
    """
    Retrieves project-scoped context chunks for generation.

    MVP uses keyword search over stored document chunks. A vector store can later
    replace the repository query while keeping this service contract stable.
    """

    def __init__(self, document_repository: DocumentRepository | None = None) -> None:
        self.document_repository = document_repository

    async def search(
        self,
        project_id: str,
        permission_scope: list[str],
        query: str,
        top_k: int = 200,
        document_ids: list[str] | None = None,
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

        # TODO: Replace keyword search with pgvector/OpenSearch similarity search
        # while keeping project_id and permission_scope filters mandatory.
        chunks = await self.document_repository.search_chunks_by_project(
            project_id=project_id,
            query=query,
            limit=top_k,
            document_ids=document_ids,
        )
        if not chunks and query:
            chunks = await self.document_repository.search_chunks_by_project(
                project_id=project_id,
                query="",
                limit=top_k,
                document_ids=document_ids,
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


retrieval_service = RetrievalService()
