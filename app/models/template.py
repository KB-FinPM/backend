# EN: SQLAlchemy model for admin-managed and built-in artifact templates.
# KO: 관리자 등록 및 기본 제공 산출물 템플릿을 위한 SQLAlchemy 모델입니다.

from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, DateTime, JSON, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class TemplateModel(Base):
    __tablename__ = "templates"
    __table_args__ = (
        UniqueConstraint(
            "template_id",
            "template_version",
            name="uq_templates_template_version",
        ),
    )

    template_pk: Mapped[str] = mapped_column(String(64), primary_key=True)
    template_id: Mapped[str] = mapped_column(String(120), index=True, nullable=False)
    template_version: Mapped[str] = mapped_column(String(80), nullable=False)
    artifact_type: Mapped[str] = mapped_column(String(80), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    placeholders: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    is_builtin: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
