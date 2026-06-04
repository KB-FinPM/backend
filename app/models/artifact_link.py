# EN: SQLAlchemy model for traceability links between generated artifacts.
# KO: 생성 산출물 간 추적 관계를 저장하는 SQLAlchemy 모델입니다.

from datetime import datetime
from typing import Any, Optional

from sqlalchemy import DateTime, ForeignKey, Index, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.types import JSONBType


class ArtifactLinkModel(Base):
    __tablename__ = "artifact_links"
    __table_args__ = (
        UniqueConstraint(
            "project_id",
            "source_artifact_id",
            "source_item_id",
            "target_artifact_id",
            "target_item_id",
            "relation_type",
            name="uq_artifact_links_relation",
        ),
        Index("ix_artifact_links_project_source", "project_id", "source_artifact_id"),
        Index("ix_artifact_links_project_target", "project_id", "target_artifact_id"),
        Index("ix_artifact_links_relation_type", "relation_type"),
    )

    link_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    project_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("projects.project_id"),
        index=True,
        nullable=False,
    )
    source_artifact_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("artifacts.artifact_id"),
        nullable=False,
    )
    source_item_id: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    target_artifact_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("artifacts.artifact_id"),
        nullable=False,
    )
    target_item_id: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    relation_type: Mapped[str] = mapped_column(String(80), nullable=False)
    link_metadata: Mapped[dict[str, Any]] = mapped_column(JSONBType, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
