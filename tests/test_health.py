from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError

from app.api.deps import get_db
from app.main import app


def test_health_returns_ok(client: TestClient) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_ready_returns_200_when_database_is_up(client: TestClient) -> None:
    # Needs the Compose database running (docker compose up -d).
    response = client.get("/ready")
    assert response.status_code == 200
    assert response.json() == {"status": "ready"}


def test_ready_returns_503_without_leaking_details_when_database_is_down(
    client: TestClient,
) -> None:
    class BrokenSession:
        def execute(self, *args, **kwargs):
            raise OperationalError("SELECT 1", {}, Exception("secret host details"))

    app.dependency_overrides[get_db] = lambda: BrokenSession()

    response = client.get("/ready")

    assert response.status_code == 503
    assert response.json() == {"status": "unavailable"}
    assert "secret" not in response.text