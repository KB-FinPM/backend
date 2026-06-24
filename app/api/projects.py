from fastapi import APIRouter, Body, Depends, Query, status

from app.core.auth import CurrentUser, assert_project_access
from app.core.exceptions import ApiError
from app.dependencies import get_current_user, get_project_service, get_schedule_service
from app.schemas.project import ProjectCreate, ProjectMetadata, ProjectUpdate
from app.schemas.response import ErrorResponse
from app.schemas.todo import (
    TodoImportCommitRequest,
    TodoImportCommitResponse,
    TodoImportPreviewRequest,
    TodoImportPreviewResponse,
    TodoItem,
    TodoListResponse,
    TodoUpdateRequest,
)
from app.services.project_service import ProjectService
from app.services.schedule_service import ScheduleService

router = APIRouter()

PROJECT_ERROR_RESPONSES = {
    status.HTTP_404_NOT_FOUND: {"model": ErrorResponse},
    status.HTTP_409_CONFLICT: {"model": ErrorResponse},
    status.HTTP_422_UNPROCESSABLE_ENTITY: {"model": ErrorResponse},
    status.HTTP_500_INTERNAL_SERVER_ERROR: {"model": ErrorResponse},
}


@router.post(
    "/projects",
    response_model=ProjectMetadata,
    status_code=status.HTTP_201_CREATED,
    responses=PROJECT_ERROR_RESPONSES,
)
async def create_project(
    request: ProjectCreate = Body(...),
    current_user: CurrentUser = Depends(get_current_user),
    project_service: ProjectService = Depends(get_project_service),
) -> ProjectMetadata:
    assert_project_access(current_user, request.project_id, "project:write")
    if not request.created_by:
        request.created_by = current_user.user_id
    return await project_service.create_project(request)


@router.get(
    "/projects",
    response_model=list[ProjectMetadata],
    responses=PROJECT_ERROR_RESPONSES,
)
async def list_projects(
    current_user: CurrentUser = Depends(get_current_user),
    project_service: ProjectService = Depends(get_project_service),
) -> list[ProjectMetadata]:
    assert_project_access(current_user, "*", "project:read")
    return await project_service.list_projects()


@router.get(
    "/projects/{project_id}",
    response_model=ProjectMetadata,
    responses=PROJECT_ERROR_RESPONSES,
)
async def get_project(
    project_id: str,
    current_user: CurrentUser = Depends(get_current_user),
    project_service: ProjectService = Depends(get_project_service),
) -> ProjectMetadata:
    assert_project_access(current_user, project_id, "project:read")
    project = await project_service.get_project(project_id)
    if project is None:
        raise ApiError(
            status_code=status.HTTP_404_NOT_FOUND,
            error_code="PROJECT_NOT_FOUND",
            message="project not found",
            detail={"project_id": project_id},
        )
    return project


@router.patch(
    "/projects/{project_id}",
    response_model=ProjectMetadata,
    responses=PROJECT_ERROR_RESPONSES,
)
async def update_project(
    project_id: str,
    request: ProjectUpdate = Body(...),
    current_user: CurrentUser = Depends(get_current_user),
    project_service: ProjectService = Depends(get_project_service),
) -> ProjectMetadata:
    assert_project_access(current_user, project_id, "project:write")
    project = await project_service.update_project(project_id, request)
    if project is None:
        raise ApiError(
            status_code=status.HTTP_404_NOT_FOUND,
            error_code="PROJECT_NOT_FOUND",
            message="project not found",
            detail={"project_id": project_id},
        )
    return project


@router.get(
    "/projects/{project_id}/todos",
    response_model=TodoListResponse,
    responses=PROJECT_ERROR_RESPONSES,
)
async def list_project_todos(
    project_id: str,
    status_filter: str | None = Query(default=None, alias="status"),
    source_type: str | None = Query(default=None),
    date_from: str | None = Query(default=None, alias="from"),
    date_to: str | None = Query(default=None, alias="to"),
    current_user: CurrentUser = Depends(get_current_user),
    schedule_service: ScheduleService = Depends(get_schedule_service),
) -> TodoListResponse:
    assert_project_access(current_user, project_id, "project:read")
    return await schedule_service.list_todos(
        project_id=project_id,
        status_filter=status_filter,
        source_type=source_type,
        date_from=date_from,
        date_to=date_to,
    )


@router.patch(
    "/projects/{project_id}/todos/{todo_id}",
    response_model=TodoItem,
    responses=PROJECT_ERROR_RESPONSES,
)
async def update_project_todo(
    project_id: str,
    todo_id: str,
    request: TodoUpdateRequest = Body(...),
    current_user: CurrentUser = Depends(get_current_user),
    schedule_service: ScheduleService = Depends(get_schedule_service),
) -> TodoItem:
    assert_project_access(current_user, project_id, "schedule:write")
    todo = await schedule_service.update_todo(
        project_id=project_id,
        todo_id=todo_id,
        values=request.model_dump(exclude_unset=True),
    )
    if todo is None:
        raise ApiError(
            status_code=status.HTTP_404_NOT_FOUND,
            error_code="TODO_NOT_FOUND",
            message="TODO not found",
            detail={"project_id": project_id, "todo_id": todo_id},
        )
    return todo


@router.delete(
    "/projects/{project_id}/todos/{todo_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses=PROJECT_ERROR_RESPONSES,
)
async def delete_project_todo(
    project_id: str,
    todo_id: str,
    current_user: CurrentUser = Depends(get_current_user),
    schedule_service: ScheduleService = Depends(get_schedule_service),
) -> None:
    assert_project_access(current_user, project_id, "schedule:write")
    deleted = await schedule_service.delete_todo(project_id=project_id, todo_id=todo_id)
    if not deleted:
        raise ApiError(
            status_code=status.HTTP_404_NOT_FOUND,
            error_code="TODO_NOT_FOUND",
            message="TODO not found",
            detail={"project_id": project_id, "todo_id": todo_id},
        )


@router.post(
    "/projects/{project_id}/todos/import/preview",
    response_model=TodoImportPreviewResponse,
    responses=PROJECT_ERROR_RESPONSES,
)
async def preview_project_todo_import(
    project_id: str,
    request: TodoImportPreviewRequest = Body(...),
    current_user: CurrentUser = Depends(get_current_user),
    schedule_service: ScheduleService = Depends(get_schedule_service),
) -> TodoImportPreviewResponse:
    assert_project_access(current_user, project_id, "schedule:write")
    preview = await schedule_service.preview_todo_import(
        project_id=project_id,
        document_id=request.document_id,
        document_type=request.document_type,
    )
    if preview.metadata.get("error") == "DOCUMENT_NOT_FOUND":
        raise ApiError(
            status_code=status.HTTP_404_NOT_FOUND,
            error_code="DOCUMENT_NOT_FOUND",
            message="document not found",
            detail={"project_id": project_id, "document_id": request.document_id},
        )
    return preview


@router.post(
    "/projects/{project_id}/todos/import/commit",
    response_model=TodoImportCommitResponse,
    responses=PROJECT_ERROR_RESPONSES,
)
async def commit_project_todo_import(
    project_id: str,
    request: TodoImportCommitRequest = Body(...),
    current_user: CurrentUser = Depends(get_current_user),
    schedule_service: ScheduleService = Depends(get_schedule_service),
) -> TodoImportCommitResponse:
    assert_project_access(current_user, project_id, "schedule:write")
    return await schedule_service.commit_todo_import(
        project_id=project_id,
        items=[item.model_dump(mode="json") for item in request.items],
        duplicate_decisions=request.duplicate_decisions,
    )
