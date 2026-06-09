# EN: Repository for chat conversations, messages, and pending actions.

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.conversation import (
    ConversationActionModel,
    ConversationMessageModel,
    ConversationModel,
)
from app.repositories.project_repository import ensure_project
from app.schemas.chat import (
    ChatActionMetadata,
    ChatActionStatus,
    ChatActionType,
    ChatMessageMetadata,
    ChatRole,
    ConversationMetadata,
    ConversationStatus,
)


class ConversationRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create_conversation(
        self,
        *,
        conversation_id: str,
        project_id: str,
        user_id: str | None = None,
        title: str | None = None,
        status: ConversationStatus = ConversationStatus.ACTIVE,
    ) -> ConversationMetadata:
        await ensure_project(self.session, project_id=project_id)
        conversation = ConversationModel(
            conversation_id=conversation_id,
            project_id=project_id,
            user_id=user_id,
            title=title,
            status=status.value,
        )
        self.session.add(conversation)
        await self.session.commit()
        await self.session.refresh(conversation)
        return self._to_conversation_metadata(conversation)

    async def get_conversation(
        self,
        *,
        project_id: str,
        conversation_id: str,
    ) -> ConversationMetadata | None:
        statement = select(ConversationModel).where(
            ConversationModel.project_id == project_id,
            ConversationModel.conversation_id == conversation_id,
        )
        result = await self.session.execute(statement)
        conversation = result.scalar_one_or_none()
        if conversation is None:
            return None
        return self._to_conversation_metadata(conversation)

    async def add_message(
        self,
        *,
        message_id: str,
        conversation_id: str,
        project_id: str,
        role: ChatRole,
        content: str,
        structured_payload: dict[str, Any] | None = None,
    ) -> ChatMessageMetadata:
        message = ConversationMessageModel(
            message_id=message_id,
            conversation_id=conversation_id,
            project_id=project_id,
            role=role.value,
            content=content,
            structured_payload=structured_payload or {},
        )
        self.session.add(message)
        await self.session.commit()
        await self.session.refresh(message)
        return self._to_message_metadata(message)

    async def create_action(
        self,
        *,
        action_id: str,
        conversation_id: str,
        project_id: str,
        action_type: ChatActionType,
        payload: dict[str, Any],
        status: ChatActionStatus = ChatActionStatus.WAITING_CONFIRMATION,
    ) -> ChatActionMetadata:
        action = ConversationActionModel(
            action_id=action_id,
            conversation_id=conversation_id,
            project_id=project_id,
            action_type=action_type.value,
            status=status.value,
            payload=payload,
            result_json={},
        )
        self.session.add(action)
        await self.session.commit()
        await self.session.refresh(action)
        return self._to_action_metadata(action)

    async def get_action(
        self,
        *,
        project_id: str,
        action_id: str,
    ) -> ChatActionMetadata | None:
        statement = select(ConversationActionModel).where(
            ConversationActionModel.project_id == project_id,
            ConversationActionModel.action_id == action_id,
        )
        result = await self.session.execute(statement)
        action = result.scalar_one_or_none()
        if action is None:
            return None
        return self._to_action_metadata(action)

    async def get_latest_waiting_action(
        self,
        *,
        project_id: str,
        conversation_id: str,
    ) -> ChatActionMetadata | None:
        statement = (
            select(ConversationActionModel)
            .where(
                ConversationActionModel.project_id == project_id,
                ConversationActionModel.conversation_id == conversation_id,
                ConversationActionModel.status
                == ChatActionStatus.WAITING_CONFIRMATION.value,
            )
            .order_by(ConversationActionModel.created_at.desc())
            .limit(1)
        )
        result = await self.session.execute(statement)
        action = result.scalar_one_or_none()
        if action is None:
            return None
        return self._to_action_metadata(action)

    async def update_action_status(
        self,
        *,
        project_id: str,
        action_id: str,
        status: ChatActionStatus,
        result_json: dict[str, Any] | None = None,
    ) -> ChatActionMetadata | None:
        statement = select(ConversationActionModel).where(
            ConversationActionModel.project_id == project_id,
            ConversationActionModel.action_id == action_id,
        )
        result = await self.session.execute(statement)
        action = result.scalar_one_or_none()
        if action is None:
            return None

        action.status = status.value
        if result_json is not None:
            action.result_json = result_json
        await self.session.commit()
        await self.session.refresh(action)
        return self._to_action_metadata(action)

    def _to_conversation_metadata(
        self,
        conversation: ConversationModel,
    ) -> ConversationMetadata:
        return ConversationMetadata(
            conversation_id=conversation.conversation_id,
            project_id=conversation.project_id,
            user_id=conversation.user_id,
            title=conversation.title,
            status=ConversationStatus(conversation.status),
        )

    def _to_message_metadata(
        self,
        message: ConversationMessageModel,
    ) -> ChatMessageMetadata:
        return ChatMessageMetadata(
            message_id=message.message_id,
            conversation_id=message.conversation_id,
            project_id=message.project_id,
            role=ChatRole(message.role),
            content=message.content,
            structured_payload=message.structured_payload or {},
        )

    def _to_action_metadata(
        self,
        action: ConversationActionModel,
    ) -> ChatActionMetadata:
        return ChatActionMetadata(
            action_id=action.action_id,
            conversation_id=action.conversation_id,
            project_id=action.project_id,
            action_type=ChatActionType(action.action_type),
            status=ChatActionStatus(action.status),
            payload=action.payload or {},
            result_json=action.result_json or {},
        )
