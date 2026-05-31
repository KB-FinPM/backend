# EN: Tests for artifact link repository persistence behavior.
# KO: 산출물 관계 Repository 저장/조회 테스트입니다.

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.repositories.artifact_link_repository import ArtifactLinkRepository
from app.schemas.traceability import ArtifactRelationType


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
async def test_artifact_link_repository_creates_and_lists_project_links(
    session_factory,
) -> None:
    async with session_factory() as session:
        repository = ArtifactLinkRepository(session)
        created = await repository.create_link(
            link_id="LINK-001",
            project_id="PRJ-001",
            source_artifact_id="ART-REQ-001",
            source_item_id="RQ-001",
            target_artifact_id="ART-WBS-001",
            target_item_id="WBS-001",
            relation_type=ArtifactRelationType.DECOMPOSED_TO,
            metadata={"confidence": 0.9},
        )

        links = await repository.list_links_by_project(project_id="PRJ-001")

    assert created.link_id == "LINK-001"
    assert links == [created]
    assert links[0].metadata == {"confidence": 0.9}


@pytest.mark.anyio
async def test_artifact_link_repository_scopes_links_by_artifact(
    session_factory,
) -> None:
    async with session_factory() as session:
        repository = ArtifactLinkRepository(session)
        await repository.create_link(
            link_id="LINK-001",
            project_id="PRJ-001",
            source_artifact_id="ART-REQ-001",
            target_artifact_id="ART-WBS-001",
            relation_type=ArtifactRelationType.DECOMPOSED_TO,
        )
        await repository.create_link(
            link_id="LINK-002",
            project_id="PRJ-002",
            source_artifact_id="ART-REQ-001",
            target_artifact_id="ART-WBS-002",
            relation_type=ArtifactRelationType.DECOMPOSED_TO,
        )

        links = await repository.list_links_for_artifact(
            project_id="PRJ-001",
            artifact_id="ART-REQ-001",
        )

    assert len(links) == 1
    assert links[0].link_id == "LINK-001"
