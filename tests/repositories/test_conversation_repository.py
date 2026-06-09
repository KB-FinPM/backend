# EN: Tests for chat conversation repository persistence behavior.

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.repositories.conversation_repository import ConversationRepository
from app.schemas.chat import ChatActionStatus, ChatActionType, ChatRole


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
async def test_conversation_repository_stores_messages_and_pending_actions(
    session_factory,
) -> None:
    async with session_factory() as session:
        repository = ConversationRepository(session)
        conversation = await repository.create_conversation(
            conversation_id="CONV-001",
            project_id="PRJ-001",
            user_id="USER-001",
            title="WBS 생성",
        )
        message = await repository.add_message(
            message_id="MSG-001",
            conversation_id=conversation.conversation_id,
            project_id="PRJ-001",
            role=ChatRole.USER,
            content="WBS 만들어줘",
        )
        action = await repository.create_action(
            action_id="ACT-001",
            conversation_id=conversation.conversation_id,
            project_id="PRJ-001",
            action_type=ChatActionType.GENERATE_WBS,
            payload={"target_artifact_type": "WBS"},
        )
        waiting_action = await repository.get_latest_waiting_action(
            project_id="PRJ-001",
            conversation_id=conversation.conversation_id,
        )
        updated = await repository.update_action_status(
            project_id="PRJ-001",
            action_id=action.action_id,
            status=ChatActionStatus.EXECUTED,
            result_json={"ok": True},
        )

    assert conversation.project_id == "PRJ-001"
    assert message.role == ChatRole.USER
    assert waiting_action is not None
    assert waiting_action.action_id == "ACT-001"
    assert updated is not None
    assert updated.status == ChatActionStatus.EXECUTED
    assert updated.result_json == {"ok": True}
