import pytest

from app.core.auth import CurrentUser, assert_project_access, resolve_user_permissions
from app.core.exceptions import ApiError


def test_resolve_user_permissions_uses_server_side_scope() -> None:
    permissions = resolve_user_permissions(
        CurrentUser(user_id="USER-001"),
        "PRJ-001",
    )

    assert permissions.project_id == "PRJ-001"
    assert "project:read" in permissions.scopes
    assert "artifact:generate" in permissions.scopes


def test_assert_project_access_rejects_unknown_action() -> None:
    with pytest.raises(ApiError) as exc_info:
        assert_project_access(
            CurrentUser(user_id="USER-001"),
            "PRJ-001",
            "not-configured",
        )

    assert exc_info.value.error_code == "UNKNOWN_PERMISSION_ACTION"
