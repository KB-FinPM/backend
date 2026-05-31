# EN: Tests for template service lookup and default resolution.
# KO: 템플릿 서비스 조회와 기본 선택 테스트입니다.

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.repositories.template_repository import TemplateRepository
from app.schemas.artifact import ArtifactType, TemplateReference
from app.services.template_service import TemplateService


@pytest.fixture
async def session_factory():
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    yield async_sessionmaker(
        bind=engine,
        autoflush=False,
        expire_on_commit=False,
    )

    await engine.dispose()


@pytest.mark.anyio
async def test_template_service_lists_builtin_templates(session_factory) -> None:
    async with session_factory() as session:
        service = TemplateService(TemplateRepository(session))

        templates = await service.list_templates(
            artifact_type=ArtifactType.REQUIREMENT_SPEC,
        )

    assert [template.template_id for template in templates] == [
        "TPL-REQ-SPEC-DEFAULT"
    ]


@pytest.mark.anyio
async def test_template_service_resolves_default_template(session_factory) -> None:
    async with session_factory() as session:
        service = TemplateService(TemplateRepository(session))

        template = await service.resolve_template(
            reference=TemplateReference(),
            artifact_type=ArtifactType.REQUIREMENT_SPEC,
        )

    assert template is not None
    assert template.template_id == "TPL-REQ-SPEC-DEFAULT"


@pytest.mark.anyio
async def test_template_service_returns_none_for_wrong_artifact_type(
    session_factory,
) -> None:
    async with session_factory() as session:
        service = TemplateService(TemplateRepository(session))

        template = await service.resolve_template(
            reference=TemplateReference(template_id="TPL-REQ-SPEC-DEFAULT"),
            artifact_type=ArtifactType.WBS,
        )

    assert template is None
