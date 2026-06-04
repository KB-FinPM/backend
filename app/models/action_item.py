# EN: SQLAlchemy model for meeting-derived action items.
# KO: 회의록 기반 액션 아이템을 저장하는 SQLAlchemy 모델입니다.

from datetime import date, datetime
from typing import Optional

from sqlalchemy import Date, DateTime, ForeignKey, Index, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ActionItemModel(Base):
    __tablename__ = "action_items"
    __table_args__ = (
        Index("ix_action_items_project_id", "project_id"),
        Index("ix_action_items_due_date", "due_date"),
    )

    action_item_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    project_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("projects.project_id"),
        nullable=False,
    )
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    owner: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    due_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    priority: Mapped[str] = mapped_column(String(30), default="MEDIUM")
    status: Mapped[str] = mapped_column(String(30), default="OPEN")
    source_document_id: Mapped[Optional[str]] = mapped_column(
        String(64),
        ForeignKey("documents.document_id"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
