"""Shared SQLAlchemy column types for PostgreSQL-first models."""

from sqlalchemy import JSON
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.types import TypeDecorator

try:
    from pgvector.sqlalchemy import Vector as PGVector
except ImportError:  # pragma: no cover - depends on local test environment.
    PGVector = None


JSONBType = JSON().with_variant(JSONB, "postgresql")


class Vector(TypeDecorator):
    cache_ok = True
    impl = JSON
    if PGVector is not None:
        comparator_factory = PGVector.comparator_factory

    def __init__(self, dimensions: int) -> None:
        super().__init__()
        self.dimensions = dimensions

    def load_dialect_impl(self, dialect):
        if dialect.name == "postgresql":
            if PGVector is None:
                raise RuntimeError(
                    "pgvector is required for PostgreSQL vector columns. "
                    "Install the pgvector package or use SQLite for local tests."
                )
            return dialect.type_descriptor(PGVector(self.dimensions))
        return dialect.type_descriptor(JSON())

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        if dialect.name == "postgresql":
            return value
        return [float(item) for item in value]

    def process_result_value(self, value, dialect):
        return value

    def get_col_spec(self, **kw: object) -> str:
        return f"vector({self.dimensions})"
