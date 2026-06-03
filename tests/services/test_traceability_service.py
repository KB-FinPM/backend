# EN: Tests for traceability service behavior.
# KO: 산출물 관계 추적 Service 테스트입니다.

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.repositories.artifact_link_repository import ArtifactLinkRepository
from app.schemas.traceability import ArtifactLinkCreate, ArtifactRelationType
from app.services.traceability_service import TraceabilityService


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
async def test_traceability_service_creates_link_with_generated_id(
    session_factory,
) -> None:
    async with session_factory() as session:
        service = TraceabilityService(ArtifactLinkRepository(session))

        link = await service.create_link(
            ArtifactLinkCreate(
                project_id="PRJ-001",
                source_artifact_id="ART-REQ-001",
                source_item_id="RQ-001",
                target_artifact_id="ART-SCREEN-001",
                target_item_id="SCR-001",
                relation_type=ArtifactRelationType.DESIGNED_BY,
            )
        )

    assert link.link_id.startswith("LINK-")
    assert link.relation_type == ArtifactRelationType.DESIGNED_BY


def test_traceability_service_builds_wbs_links_from_generated_result() -> None:
    service = TraceabilityService(artifact_link_repository=None)

    links = service.build_links_from_generated_artifact(
        project_id="PRJ-001",
        source_artifact_id="ART-REQ-001",
        target_artifact_id="ART-WBS-001",
        generated_result={
            "artifact_type": "WBS",
            "tasks": [
                {
                    "task_id": "WBS-001",
                    "name": "Login work",
                    "source_requirement_ids": ["RQ-001", "RQ-002"],
                }
            ],
        },
    )

    assert len(links) == 2
    assert links[0].source_item_id == "RQ-001"
    assert links[0].target_item_id == "WBS-001"
    assert links[0].relation_type == ArtifactRelationType.DECOMPOSED_TO
    assert links[0].metadata["auto_generated"] is True


def test_traceability_service_builds_screen_links_from_generated_result() -> None:
    service = TraceabilityService(artifact_link_repository=None)

    links = service.build_links_from_generated_artifact(
        project_id="PRJ-001",
        source_artifact_id="ART-REQ-001",
        target_artifact_id="ART-SCREEN-001",
        generated_result={
            "artifact_type": "SCREEN_DESIGN",
            "screens": [
                {
                    "screen_id": "SCR-001",
                    "name": "Login",
                    "source_requirement_ids": ["RQ-001"],
                }
            ],
        },
    )

    assert len(links) == 1
    assert links[0].source_item_id == "RQ-001"
    assert links[0].target_item_id == "SCR-001"
    assert links[0].relation_type == ArtifactRelationType.DESIGNED_BY
