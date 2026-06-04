# EN: SQLAlchemy models for uploaded documents and searchable chunks.
# KO: 업로드 문서와 검색 가능한 Chunk를 위한 SQLAlchemy 모델입니다.

from datetime import datetime
from typing import Any, Optional

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.types import JSONBType, Vector


class DocumentModel(Base):
    __tablename__ = "documents"
    __table_args__ = (Index("ix_documents_project_type", "project_id", "document_type"),)

    document_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    project_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("projects.project_id"),
        index=True,
        nullable=False,
    )
    document_type: Mapped[str] = mapped_column(String(80), nullable=False)
    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    storage_path: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="UPLOADED")
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class DocumentChunkModel(Base):
    __tablename__ = "document_chunks"
    __table_args__ = (
        UniqueConstraint("document_id", "chunk_index", name="uq_document_chunk"),
        Index("ix_document_chunks_project_document", "project_id", "document_id"),
        Index("ix_document_chunks_document_index", "document_id", "chunk_index"),
        Index(
            "ix_document_chunks_embedding",
            "embedding",
            postgresql_using="hnsw",
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
    )

    chunk_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    project_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("projects.project_id"),
        index=True,
        nullable=False,
    )
    document_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("documents.document_id"),
        nullable=False,
    )
    section_title: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    page_no: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    text: Mapped[str] = mapped_column("chunk_text", Text, nullable=False)
    chunk_metadata: Mapped[dict[str, Any]] = mapped_column(JSONBType, default=dict)
    embedding: Mapped[Optional[list[float]]] = mapped_column(Vector(1024), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
