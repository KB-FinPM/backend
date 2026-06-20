"""Server-side authorization helpers for the MVP API surface."""

from dataclasses import dataclass

from fastapi import status

from app.core.exceptions import ApiError


@dataclass(frozen=True)
class CurrentUser:
    user_id: str


@dataclass(frozen=True)
class ProjectPermissions:
    project_id: str
    scopes: list[str]


ACTION_REQUIRED_SCOPES = {
    "project:read": {"project:read"},
    "project:write": {"project:write"},
    "document:read": {"project:read", "document:read"},
    "document:write": {"project:write", "document:write"},
    "artifact:read": {"project:read", "artifact:read"},
    "artifact:generate": {"project:read", "artifact:generate"},
    "schedule:write": {"project:read", "schedule:write"},
    "chat:write": {"project:read", "chat:write"},
}


DEFAULT_MVP_SCOPES = [
    "project:read",
    "project:write",
    "document:read",
    "document:write",
    "artifact:read",
    "artifact:generate",
    "schedule:write",
    "chat:write",
]


def resolve_user_permissions(
    user: CurrentUser,
    project_id: str,
) -> ProjectPermissions:
    """Resolve permissions on the server.

    This MVP resolver intentionally ignores client-provided permission scopes.
    Replace this function with JWT/session claims plus project membership checks
    before production use.
    """
    return ProjectPermissions(project_id=project_id, scopes=list(DEFAULT_MVP_SCOPES))


def assert_project_access(
    user: CurrentUser,
    project_id: str,
    action: str,
) -> ProjectPermissions:
    permissions = resolve_user_permissions(user, project_id)
    required_scopes = ACTION_REQUIRED_SCOPES.get(action)
    if required_scopes is None:
        raise ApiError(
            status_code=status.HTTP_403_FORBIDDEN,
            error_code="UNKNOWN_PERMISSION_ACTION",
            message="permission action is not configured",
            detail={"project_id": project_id, "action": action},
        )

    granted_scopes = set(permissions.scopes)
    if not required_scopes.issubset(granted_scopes):
        raise ApiError(
            status_code=status.HTTP_403_FORBIDDEN,
            error_code="PROJECT_ACCESS_DENIED",
            message="project access denied",
            detail={"project_id": project_id, "action": action},
        )

    return permissions
