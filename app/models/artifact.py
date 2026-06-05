# EN: SQLAlchemy model for generated project artifacts.
# KO: 생성된 프로젝트 산출물을 위한 SQLAlchemy 모델입니다.

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
from app.models.types import JSONBType


class ArtifactModel(Base):
    __tablename__ = "artifacts"
    __table_args__ = (Index("ix_artifacts_project_type", "project_id", "artifact_type"),)

    artifact_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    project_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("projects.project_id"),
        index=True,
        nullable=False,
    )
    artifact_type: Mapped[str] = mapped_column(String(80), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    latest_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    template_id: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    template_version: Mapped[Optional[str]] = mapped_column(String(80), nullable=True)
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="CREATED")
    storage_path: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
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


class ArtifactVersionModel(Base):
    __tablename__ = "artifact_versions"
    __table_args__ = (
        UniqueConstraint("artifact_id", "version", name="uq_artifact_version"),
        Index("ix_artifact_versions_artifact", "artifact_id"),
    )

    artifact_version_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    artifact_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("artifacts.artifact_id"),
        nullable=False,
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    result_json: Mapped[dict[str, Any]] = mapped_column(JSONBType, default=dict)
    markdown_content: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    validation_result: Mapped[dict[str, Any]] = mapped_column(JSONBType, default=dict)
    storage_path: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )


class ArtifactDocumentModel(Base):
    __tablename__ = "artifact_documents"
    __table_args__ = (Index("ix_artifact_documents_document", "document_id"),)

    artifact_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("artifacts.artifact_id"),
        primary_key=True,
    )
    document_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("documents.document_id"),
        primary_key=True,
    )
