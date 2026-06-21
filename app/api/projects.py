from fastapi import APIRouter, Body, Depends, status

from app.core.auth import CurrentUser, assert_project_access
from app.core.exceptions import ApiError
from app.dependencies import get_current_user, get_project_service
from app.schemas.project import ProjectCreate, ProjectMetadata, ProjectUpdate
from app.schemas.response import ErrorResponse
from app.services.project_service import ProjectService

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
