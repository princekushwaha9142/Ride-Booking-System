from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.core.config import get_settings
from app.db.session import SessionLocal
from tests.helpers import (
    DEFAULT_PASSWORD,
    auth_header,
    login,
    logout,
    make_token,
    refresh,
    register,
)


# --- Registration -----------------------------------------------------------
def test_register_returns_201_without_secrets(client: TestClient) -> None:
    response = register(client)
    assert response.status_code == 201
    body = response.json()
    assert body["email"] == "rider@example.com"
    assert body["role"] == "RIDER"
    assert body["is_active"] is True
    assert "password" not in body
    assert "password_hash" not in body


def test_password_is_stored_as_argon2_hash(client: TestClient) -> None:
    register(client)
    with SessionLocal() as db:
        stored = db.execute(text("SELECT password_hash FROM users")).scalar_one()
    assert stored.startswith("$argon2id$")
    assert DEFAULT_PASSWORD not in stored


def test_driver_can_register(client: TestClient) -> None:
    response = register(client, email="driver@example.com", role="DRIVER")
    assert response.status_code == 201
    assert response.json()["role"] == "DRIVER"


def test_duplicate_email_is_rejected_case_insensitively(client: TestClient) -> None:
    assert register(client, email="Rider@Example.com").status_code == 201
    response = register(client, email="rider@example.com")
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "conflict"


@pytest.mark.parametrize(
    "payload",
    [
        {"email": "not-an-email", "password": "CorrectHorse1", "full_name": "A"},
        {"email": "a@example.com", "password": "short", "full_name": "A"},
        {"email": "a@example.com", "password": "CorrectHorse1", "full_name": "   "},
        {"email": "a@example.com", "password": "CorrectHorse1", "full_name": "A", "role": "ADMIN"},
        {"email": "a@example.com", "password": "CorrectHorse1", "full_name": "A", "phone": "abc"},
    ],
)
def test_invalid_registration_input_returns_422_without_echoing_input(
    client: TestClient, payload: dict
) -> None:
    response = client.post("/api/v1/auth/register", json=payload)
    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "validation_error"
    assert all("input" not in detail for detail in error["details"])


# --- Login ------------------------------------------------------------------
def test_login_returns_token_pair(client: TestClient) -> None:
    register(client)
    response = login(client)
    assert response.status_code == 200
    body = response.json()
    assert body["token_type"] == "bearer"
    assert body["access_token"]
    assert body["refresh_token"]
    assert body["expires_in"] == get_settings().access_token_expire_minutes * 60


def test_login_email_is_case_insensitive(client: TestClient) -> None:
    register(client, email="Rider@Example.com")
    assert login(client, email="rider@example.com").status_code == 200


def test_login_with_wrong_password_returns_401(client: TestClient) -> None:
    register(client)
    response = login(client, password="WrongPassword1")
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthorized"


def test_unknown_email_and_wrong_password_give_identical_errors(client: TestClient) -> None:
    register(client)
    wrong_password = login(client, password="WrongPassword1")
    unknown_email = login(client, email="nobody@example.com")
    assert unknown_email.status_code == wrong_password.status_code == 401
    assert unknown_email.json() == wrong_password.json()


def test_refresh_token_is_stored_only_as_hash(client: TestClient, rider_tokens: dict) -> None:
    with SessionLocal() as db:
        stored = db.execute(text("SELECT token_hash FROM refresh_tokens")).scalar_one()
    assert stored != rider_tokens["refresh_token"]
    assert len(stored) == 64


# --- Current user -----------------------------------------------------------
def test_me_returns_current_user(client: TestClient, rider_tokens: dict) -> None:
    response = client.get("/api/v1/users/me", headers=auth_header(rider_tokens["access_token"]))
    assert response.status_code == 200
    assert response.json()["email"] == "rider@example.com"


def test_me_without_token_returns_401(client: TestClient) -> None:
    response = client.get("/api/v1/users/me")
    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"


def test_me_with_garbage_token_returns_401(client: TestClient) -> None:
    response = client.get("/api/v1/users/me", headers=auth_header("not.a.jwt"))
    assert response.status_code == 401


def test_me_with_expired_token_returns_401(client: TestClient) -> None:
    user_id = register(client).json()["id"]
    token = make_token(user_id, expires_in=timedelta(minutes=-1))
    assert client.get("/api/v1/users/me", headers=auth_header(token)).status_code == 401


def test_me_with_token_signed_by_wrong_key_returns_401(client: TestClient) -> None:
    user_id = register(client).json()["id"]
    token = make_token(user_id, key="y" * 40)
    assert client.get("/api/v1/users/me", headers=auth_header(token)).status_code == 401


def test_deactivated_user_loses_access_immediately(client: TestClient, rider_tokens: dict) -> None:
    with SessionLocal() as db:
        db.execute(text("UPDATE users SET is_active = false"))
        db.commit()

    me = client.get("/api/v1/users/me", headers=auth_header(rider_tokens["access_token"]))
    assert me.status_code == 401
    assert login(client).status_code == 403
    assert refresh(client, rider_tokens["refresh_token"]).status_code == 401


# --- Refresh rotation -------------------------------------------------------
def test_refresh_rotates_the_refresh_token(client: TestClient, rider_tokens: dict) -> None:
    response = refresh(client, rider_tokens["refresh_token"])
    assert response.status_code == 200
    new_tokens = response.json()
    assert new_tokens["refresh_token"] != rider_tokens["refresh_token"]

    me = client.get("/api/v1/users/me", headers=auth_header(new_tokens["access_token"]))
    assert me.status_code == 200


def test_reusing_a_rotated_refresh_token_revokes_the_whole_family(
    client: TestClient, rider_tokens: dict
) -> None:
    first = refresh(client, rider_tokens["refresh_token"])
    assert first.status_code == 200
    newest = first.json()["refresh_token"]

    replay = refresh(client, rider_tokens["refresh_token"])  # old token comes back
    assert replay.status_code == 401

    # The legitimate newest token was revoked too (family kill).
    assert refresh(client, newest).status_code == 401


def test_refresh_with_unknown_token_returns_401(client: TestClient) -> None:
    assert refresh(client, "definitely-not-a-real-token").status_code == 401


def test_refresh_with_expired_token_returns_401(client: TestClient, rider_tokens: dict) -> None:
    with SessionLocal() as db:
        db.execute(text("UPDATE refresh_tokens SET expires_at = now() - interval '1 minute'"))
        db.commit()
    assert refresh(client, rider_tokens["refresh_token"]).status_code == 401


# --- Logout -----------------------------------------------------------------
def test_logout_revokes_the_session(client: TestClient, rider_tokens: dict) -> None:
    assert logout(client, rider_tokens["refresh_token"]).status_code == 204
    assert refresh(client, rider_tokens["refresh_token"]).status_code == 401


def test_logout_is_idempotent_and_ignores_unknown_tokens(
    client: TestClient, rider_tokens: dict
) -> None:
    assert logout(client, rider_tokens["refresh_token"]).status_code == 204
    assert logout(client, rider_tokens["refresh_token"]).status_code == 204
    assert logout(client, "never-issued").status_code == 204