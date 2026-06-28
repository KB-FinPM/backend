# EN: SQLAlchemy model for project metadata.
# KO: 프로젝트 메타데이터를 저장하는 SQLAlchemy 모델입니다.

from datetime import date, datetime
from typing import Optional

from sqlalchemy import Date, DateTime, Index, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ProjectModel(Base):
    __tablename__ = "projects"
    __table_args__ = (Index("ix_projects_status", "status"),)

    project_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    project_name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    start_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    end_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="ACTIVE")
    created_by: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    document_author: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
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
