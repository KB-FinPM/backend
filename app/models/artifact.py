# EN: SQLAlchemy model for generated project artifacts.
# KO: 생성된 프로젝트 산출물을 위한 SQLAlchemy 모델입니다.

from datetime import datetime
from typing import Any, Optional

from sqlalchemy import DateTime, Integer, JSON, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ArtifactModel(Base):
    __tablename__ = "artifacts"

    artifact_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    project_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    artifact_type: Mapped[str] = mapped_column(String(80), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    source_document_ids: Mapped[list[str]] = mapped_column(JSON, default=list)
    template_id: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    template_version: Mapped[Optional[str]] = mapped_column(String(80), nullable=True)
    result_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    storage_path: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="CREATED")
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
