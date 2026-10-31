import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from app.api.deps import require_roles
from app.core.exceptions import register_exception_handlers
from app.db.models.user import Role, User
from tests.helpers import auth_header, create_user_in_db, login

# A tiny app that exists only to test the guard (real admin endpoints arrive in Phase 4).
guard_app = FastAPI()
register_exception_handlers(guard_app)


@guard_app.get("/admin-only")
def admin_only(user: User = Depends(require_roles(Role.ADMIN))) -> dict[str, str]:
    return {"id": str(user.id)}


@pytest.mark.parametrize(
    "role, expected_status",
    [("RIDER", 403), ("DRIVER", 403), ("ADMIN", 200)],
)
def test_admin_only_route_by_role(client: TestClient, role: str, expected_status: int) -> None:
    email = f"{role.lower()}@example.com"
    create_user_in_db(email=email, role=role)
    token = login(client, email=email).json()["access_token"]

    response = TestClient(guard_app).get("/admin-only", headers=auth_header(token))

    assert response.status_code == expected_status
    if expected_status == 403:
        assert response.json()["error"]["code"] == "forbidden"


def test_guard_without_token_returns_401() -> None:
    assert TestClient(guard_app).get("/admin-only").status_code == 401