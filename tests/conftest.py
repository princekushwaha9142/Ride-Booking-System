import os
from collections.abc import Iterator

from dotenv import dotenv_values

# Must run BEFORE importing the app: point the app at the isolated test DB.
_DEFAULT_TEST_URL = (
    "postgresql+psycopg://ride:change_me_local_only@localhost:5432/ride_booking_test"
)
_env_file = dotenv_values(".env")
os.environ["ENVIRONMENT"] = "test"
os.environ["DATABASE_URL"] = (
    os.getenv("TEST_DATABASE_URL")
    or _env_file.get("TEST_DATABASE_URL")
    or _DEFAULT_TEST_URL
)

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402


@pytest.fixture()
def client() -> Iterator[TestClient]:
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()