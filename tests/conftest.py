import os
from collections.abc import Iterator
from pathlib import Path

from dotenv import dotenv_values
from sqlalchemy.engine import make_url

# --- Must run BEFORE importing the app: point everything at the isolated test DB ---
_DEFAULT_TEST_URL = (
    "postgresql+psycopg://ride:change_me_local_only@localhost:5433/ride_booking_test"
)
_env_file = dotenv_values(".env")
_test_url = (
    os.getenv("TEST_DATABASE_URL")
    or _env_file.get("TEST_DATABASE_URL")
    or _DEFAULT_TEST_URL
)

# Safety net: the suite TRUNCATES tables, so refuse to run on anything not named *_test.
if not (make_url(_test_url).database or "").endswith("_test"):
    raise RuntimeError("Refusing to run tests: the test database name must end with '_test'")

os.environ["ENVIRONMENT"] = "test"
os.environ["DATABASE_URL"] = _test_url
os.environ["SECRET_KEY"] = "test-only-secret-key-not-for-production-0123456789"

import pytest  # noqa: E402
from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import text  # noqa: E402

from app.db.session import engine  # noqa: E402
from app.main import app  # noqa: E402
from tests.helpers import login, register  # noqa: E402

_ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture(scope="session", autouse=True)
def apply_migrations() -> None:
    """Build the test schema with the REAL migrations, so migrations are tested too."""
    cfg = Config(str(_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(_ROOT / "alembic"))
    command.upgrade(cfg, "head")


@pytest.fixture(autouse=True)
def clean_database(apply_migrations: None) -> None:
    """Every test starts from empty tables, so tests are independent and deterministic."""
    with engine.begin() as conn:
        conn.execute(text("TRUNCATE TABLE refresh_tokens, users RESTART IDENTITY CASCADE"))


@pytest.fixture()
def client() -> Iterator[TestClient]:
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture()
def rider_tokens(client: TestClient) -> dict:
    """A registered and logged-in rider; returns the token response body."""
    assert register(client).status_code == 201
    response = login(client)
    assert response.status_code == 200
    return response.json()