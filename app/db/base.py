# EN: Declarative base and model registry imports for SQLAlchemy metadata.
# KO: SQLAlchemy 메타데이터 구성을 위한 Declarative Base와 모델 등록 파일입니다.

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


# Import models so Base.metadata can discover them for local initialization.
from app.models.action_item import ActionItemModel  # noqa: E402, F401
from app.models.artifact import (  # noqa: E402, F401
    ArtifactDocumentModel,
    ArtifactModel,
    ArtifactVersionModel,
)
from app.models.artifact_link import ArtifactLinkModel  # noqa: E402, F401
from app.models.document import DocumentChunkModel, DocumentModel  # noqa: E402, F401
from app.models.project import ProjectModel  # noqa: E402, F401
from app.models.template import TemplateModel  # noqa: E402, F401
