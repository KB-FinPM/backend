# EN: FastAPI dependency factories for repositories and shared resources.
# KO: Repository 및 공통 리소스를 제공하는 FastAPI 의존성 팩토리입니다.

from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import Depends

from app.db.session import get_session
from app.orchestrator.input_orchestrator import InputOrchestrator, input_orchestrator
from app.orchestrator.chat_orchestrator import ChatOrchestrator
from app.orchestrator.output_orchestrator import (
    OutputOrchestrator,
    output_orchestrator,
)
from app.repositories.artifact_repository import ArtifactRepository
from app.repositories.artifact_link_repository import ArtifactLinkRepository
from app.repositories.conversation_repository import ConversationRepository
from app.repositories.document_repository import DocumentRepository
from app.repositories.template_repository import TemplateRepository
from app.orchestrator.generation_orchestrator import generation_orchestrator
from app.rag.retrieval import RetrievalService
from app.services.artifact_service import ArtifactService
from app.services.chat_service import ChatService
from app.services.document_service import DocumentService
from app.services.generation_service import GenerationService
from app.services.schedule_service import ScheduleService
from app.services.template_service import TemplateService
from app.services.traceability_service import TraceabilityService
from app.storage.s3 import s3_service


def get_document_repository(
    session: AsyncSession = Depends(get_session),
) -> DocumentRepository:
    return DocumentRepository(session)


def get_artifact_repository(
    session: AsyncSession = Depends(get_session),
) -> ArtifactRepository:
    return ArtifactRepository(session)


def get_artifact_link_repository(
    session: AsyncSession = Depends(get_session),
) -> ArtifactLinkRepository:
    return ArtifactLinkRepository(session)


def get_conversation_repository(
    session: AsyncSession = Depends(get_session),
) -> ConversationRepository:
    return ConversationRepository(session)


def get_template_repository(
    session: AsyncSession = Depends(get_session),
) -> TemplateRepository:
    return TemplateRepository(session)


def get_document_service(
    document_repository: DocumentRepository = Depends(get_document_repository),
) -> DocumentService:
    return DocumentService(document_repository, s3_service)


def get_artifact_service(
    artifact_repository: ArtifactRepository = Depends(get_artifact_repository),
) -> ArtifactService:
    return ArtifactService(artifact_repository)


def get_generation_service() -> GenerationService:
    return GenerationService(generation_orchestrator)


def get_schedule_service() -> ScheduleService:
    return ScheduleService()


def get_retrieval_service(
    document_repository: DocumentRepository = Depends(get_document_repository),
) -> RetrievalService:
    return RetrievalService(document_repository)


def get_template_service(
    template_repository: TemplateRepository = Depends(get_template_repository),
) -> TemplateService:
    return TemplateService(template_repository)


def get_traceability_service(
    artifact_link_repository: ArtifactLinkRepository = Depends(
        get_artifact_link_repository
    ),
) -> TraceabilityService:
    return TraceabilityService(artifact_link_repository)


def get_input_orchestrator() -> InputOrchestrator:
    return input_orchestrator


def get_output_orchestrator() -> OutputOrchestrator:
    return output_orchestrator


def get_chat_service(
    conversation_repository: ConversationRepository = Depends(
        get_conversation_repository
    ),
    generation_service: GenerationService = Depends(get_generation_service),
    schedule_service: ScheduleService = Depends(get_schedule_service),
    document_service: DocumentService = Depends(get_document_service),
    artifact_service: ArtifactService = Depends(get_artifact_service),
    retrieval_service: RetrievalService = Depends(get_retrieval_service),
    template_service: TemplateService = Depends(get_template_service),
    input_orchestrator: InputOrchestrator = Depends(get_input_orchestrator),
    output_orchestrator: OutputOrchestrator = Depends(get_output_orchestrator),
) -> ChatService:
    return ChatService(
        ChatOrchestrator(
            conversation_repository=conversation_repository,
            generation_service=generation_service,
            schedule_service=schedule_service,
            document_service=document_service,
            artifact_service=artifact_service,
            retrieval_service=retrieval_service,
            template_service=template_service,
            input_normalizer=input_orchestrator,
            output_formatter=output_orchestrator,
        )
    )
