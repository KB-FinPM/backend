# EN: Shared SQLAlchemy column types for PostgreSQL-first models.
# KO: PostgreSQL 중심 모델에서 공통으로 쓰는 SQLAlchemy 컬럼 타입입니다.

from sqlalchemy import JSON
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.types import UserDefinedType


JSONBType = JSON().with_variant(JSONB, "postgresql")


class Vector(UserDefinedType):
    cache_ok = True

    def __init__(self, dimensions: int) -> None:
        self.dimensions = dimensions

    def get_col_spec(self, **kw: object) -> str:
        return f"vector({self.dimensions})"
