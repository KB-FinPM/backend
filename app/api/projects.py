from fastapi import APIRouter, Body, Depends, status

from app.core.exceptions import ApiError
from app.dependencies import get_project_service
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
    project_service: ProjectService = Depends(get_project_service),
) -> ProjectMetadata:
    return await project_service.create_project(request)


@router.get(
    "/projects",
    response_model=list[ProjectMetadata],
    responses=PROJECT_ERROR_RESPONSES,
)
async def list_projects(
    project_service: ProjectService = Depends(get_project_service),
) -> list[ProjectMetadata]:
    return await project_service.list_projects()


@router.get(
    "/projects/{project_id}",
    response_model=ProjectMetadata,
    responses=PROJECT_ERROR_RESPONSES,
)
async def get_project(
    project_id: str,
    project_service: ProjectService = Depends(get_project_service),
) -> ProjectMetadata:
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
    project_service: ProjectService = Depends(get_project_service),
) -> ProjectMetadata:
    project = await project_service.update_project(project_id, request)
    if project is None:
        raise ApiError(
            status_code=status.HTTP_404_NOT_FOUND,
            error_code="PROJECT_NOT_FOUND",
            message="project not found",
            detail={"project_id": project_id},
        )
    return project
