# EN: Repository for document metadata and document chunk persistence.
# KO: 문서 메타데이터와 문서 Chunk 저장을 담당하는 Repository입니다.

from math import sqrt
from typing import Any, Optional

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.document import DocumentChunkModel, DocumentModel
from app.repositories.project_repository import ensure_project
from app.schemas.artifact import DocumentMetadata, DocumentStatus, DocumentType


class DocumentRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create_document(
        self,
        *,
        document_id: str,
        project_id: str,
        document_type: DocumentType,
        file_name: str,
        storage_path: str,
        status: DocumentStatus = DocumentStatus.UPLOADED,
    ) -> DocumentMetadata:
        await ensure_project(self.session, project_id=project_id)
        document = DocumentModel(
            document_id=document_id,
            project_id=project_id,
            document_type=document_type.value,
            file_name=file_name,
            storage_path=storage_path,
            status=status.value,
        )
        self.session.add(document)
        await self.session.commit()
        await self.session.refresh(document)
        return self._to_metadata(document)

    async def get_document(
        self,
        *,
        project_id: str,
        document_id: str,
    ) -> Optional[DocumentMetadata]:
        statement = select(DocumentModel).where(
            DocumentModel.project_id == project_id,
            DocumentModel.document_id == document_id,
        )
        result = await self.session.execute(statement)
        document = result.scalar_one_or_none()
        if document is None:
            return None
        return self._to_metadata(document)

    async def list_documents_by_project(
        self,
        *,
        project_id: str,
    ) -> list[DocumentMetadata]:
        statement = (
            select(DocumentModel)
            .where(DocumentModel.project_id == project_id)
            .order_by(DocumentModel.created_at.desc())
        )
        result = await self.session.execute(statement)
        return [self._to_metadata(document) for document in result.scalars().all()]

    async def update_document_status(
        self,
        *,
        project_id: str,
        document_id: str,
        status: DocumentStatus,
    ) -> Optional[DocumentMetadata]:
        statement = select(DocumentModel).where(
            DocumentModel.project_id == project_id,
            DocumentModel.document_id == document_id,
        )
        result = await self.session.execute(statement)
        document = result.scalar_one_or_none()
        if document is None:
            return None

        document.status = status.value
        await self.session.commit()
        await self.session.refresh(document)

        return self._to_metadata(document)

    async def delete_document(
        self,
        *,
        project_id: str,
        document_id: str,
    ) -> bool:
        document_statement = select(DocumentModel).where(
            DocumentModel.project_id == project_id,
            DocumentModel.document_id == document_id,
        )
        result = await self.session.execute(document_statement)
        document = result.scalar_one_or_none()
        if document is None:
            return False

        await self.session.execute(
            delete(DocumentChunkModel).where(
                DocumentChunkModel.project_id == project_id,
                DocumentChunkModel.document_id == document_id,
            )
        )
        await self.session.delete(document)
        await self.session.commit()
        return True

    async def create_chunk(
        self,
        *,
        chunk_id: str,
        project_id: str,
        document_id: str,
        chunk_index: int,
        text: str,
        section_title: Optional[str] = None,
        chunk_metadata: Optional[dict[str, Any]] = None,
        embedding: Optional[list[float]] = None,
    ) -> DocumentChunkModel:
        await ensure_project(self.session, project_id=project_id)
        # PostgreSQL enforces the model's VARCHAR(255) limit strictly, so keep
        # chunk section titles within the database boundary before insert.
        normalized_section_title = self._truncate_text(section_title, 255)
        chunk = DocumentChunkModel(
            chunk_id=chunk_id,
            project_id=project_id,
            document_id=document_id,
            chunk_index=chunk_index,
            text=text,
            section_title=normalized_section_title,
            chunk_metadata=chunk_metadata or {},
            embedding=embedding,
        )
        self.session.add(chunk)
        await self.session.commit()
        await self.session.refresh(chunk)
        return chunk

    async def list_chunks_by_document(
        self,
        *,
        project_id: str,
        document_id: str,
    ) -> list[DocumentChunkModel]:
        statement = (
            select(DocumentChunkModel)
            .where(
                DocumentChunkModel.project_id == project_id,
                DocumentChunkModel.document_id == document_id,
            )
            .order_by(DocumentChunkModel.chunk_index.asc())
        )
        result = await self.session.execute(statement)
        return list(result.scalars().all())

    async def search_chunks_by_project(
        self,
        *,
        project_id: str,
        query: str,
        limit: int = 5,
        document_ids: list[str] | None = None,
        query_embedding: list[float] | None = None,
        search_mode: str = "vector",
    ) -> list[DocumentChunkModel]:
        statement = select(DocumentChunkModel).where(
            DocumentChunkModel.project_id == project_id
        )
        if document_ids:
            statement = statement.where(DocumentChunkModel.document_id.in_(document_ids))

        if query_embedding and self._supports_vector_search():
            vector_statement = (
                statement.where(DocumentChunkModel.embedding.is_not(None))
                .order_by(
                    DocumentChunkModel.embedding.cosine_distance(query_embedding)
                )
            )
            if limit and limit > 0:
                vector_statement = vector_statement.limit(limit)
            result = await self.session.execute(vector_statement)
            chunks = list(result.scalars().all())
            if chunks:
                return chunks

        if query_embedding and not self._supports_vector_search():
            candidate_limit = limit * 10 if limit and limit > 0 else None
            chunks = await self._fetch_chunks(statement, limit=candidate_limit)
            ranked = self._rank_chunks_by_embedding(
                chunks,
                query_embedding=query_embedding,
                limit=limit,
            )
            if ranked:
                return ranked

        if query:
            statement = statement.where(DocumentChunkModel.text.ilike(f"%{query}%"))
            statement = statement.order_by(DocumentChunkModel.created_at.desc())
        else:
            # Requirement generation must consume the selected document in source
            # order, not the latest N chunks. This mirrors sample_0605's
            # chunk-by-chunk pipeline.
            statement = statement.order_by(
                DocumentChunkModel.document_id.asc(),
                DocumentChunkModel.chunk_index.asc(),
            )

        return await self._fetch_chunks(statement, limit=limit)

    async def _fetch_chunks(
        self,
        statement,
        *,
        limit: int | None = None,
    ) -> list[DocumentChunkModel]:
        if limit and limit > 0:
            statement = statement.limit(limit)
        result = await self.session.execute(statement)
        return list(result.scalars().all())

    def _supports_vector_search(self) -> bool:
        bind = getattr(self.session, "bind", None)
        dialect = getattr(bind, "dialect", None)
        return bool(dialect and getattr(dialect, "name", "") == "postgresql")

    @staticmethod
    def _truncate_text(value: Optional[str], max_chars: int) -> Optional[str]:
        if value is None:
            return None
        normalized = str(value).strip()
        if not normalized:
            return None
        return normalized[:max_chars]

    def _rank_chunks_by_embedding(
        self,
        chunks: list[DocumentChunkModel],
        *,
        query_embedding: list[float],
        limit: int,
    ) -> list[DocumentChunkModel]:
        scored: list[tuple[float, DocumentChunkModel]] = []
        for chunk in chunks:
            embedding = chunk.embedding
            if not isinstance(embedding, list) or not embedding:
                continue
            score = self._cosine_similarity(query_embedding, embedding)
            scored.append((score, chunk))

        scored.sort(key=lambda item: item[0], reverse=True)
        ranked = [chunk for _, chunk in scored]
        if limit and limit > 0:
            return ranked[:limit]
        return ranked

    def _cosine_similarity(
        self,
        left: list[float],
        right: list[float],
    ) -> float:
        if not left or not right:
            return 0.0
        length = min(len(left), len(right))
        if length == 0:
            return 0.0
        dot = 0.0
        left_norm = 0.0
        right_norm = 0.0
        for index in range(length):
            l_value = float(left[index])
            r_value = float(right[index])
            dot += l_value * r_value
            left_norm += l_value * l_value
            right_norm += r_value * r_value
        if left_norm <= 0.0 or right_norm <= 0.0:
            return 0.0
        return dot / (sqrt(left_norm) * sqrt(right_norm))

    def _to_metadata(self, document: DocumentModel) -> DocumentMetadata:
        return DocumentMetadata(
            document_id=document.document_id,
            project_id=document.project_id,
            document_type=DocumentType(document.document_type),
            file_name=document.file_name,
            storage_path=document.storage_path,
            status=DocumentStatus(document.status),
            created_at=document.created_at,
            updated_at=document.updated_at,
        )
