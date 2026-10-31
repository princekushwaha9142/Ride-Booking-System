import uuid
from datetime import datetime, timedelta, timezone

import jwt
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.core.security import hash_password
from app.db.models.user import User
from app.db.session import SessionLocal

DEFAULT_EMAIL = "rider@example.com"
DEFAULT_PASSWORD = "CorrectHorse1"


def register(
    client: TestClient,
    *,
    email: str = DEFAULT_EMAIL,
    password: str = DEFAULT_PASSWORD,
    full_name: str = "Test Rider",
    role: str = "RIDER",
):
    return client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": password, "full_name": full_name, "role": role},
    )


def login(client: TestClient, *, email: str = DEFAULT_EMAIL, password: str = DEFAULT_PASSWORD):
    return client.post("/api/v1/auth/login", json={"email": email, "password": password})


def refresh(client: TestClient, refresh_token: str):
    return client.post("/api/v1/auth/refresh", json={"refresh_token": refresh_token})


def logout(client: TestClient, refresh_token: str):
    return client.post("/api/v1/auth/logout", json={"refresh_token": refresh_token})


def auth_header(access_token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {access_token}"}


def create_user_in_db(*, email: str, role: str, password: str = DEFAULT_PASSWORD) -> uuid.UUID:
    """Insert a user directly (used for roles that cannot self-register, like ADMIN)."""
    with SessionLocal() as db:
        user = User(
            email=email,
            password_hash=hash_password(password),
            full_name="Seeded User",
            role=role,
        )
        db.add(user)
        db.commit()
        return user.id


def make_token(
    sub: uuid.UUID | str,
    *,
    expires_in: timedelta = timedelta(minutes=5),
    token_type: str = "access",
    key: str | None = None,
) -> str:
    """Build a JWT by hand, to test expired / wrong-key / wrong-type tokens."""
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(sub),
        "type": token_type,
        "iat": now - timedelta(hours=1),
        "exp": now + expires_in,
    }
    return jwt.encode(payload, key or get_settings().secret_key, algorithm="HS256")