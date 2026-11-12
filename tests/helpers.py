import uuid
from datetime import datetime, timedelta, timezone

import jwt
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.core.security import hash_password
from app.db.models.user import User
from app.db.session import SessionLocal
from contextlib import contextmanager

from sqlalchemy import event, text

from app.db.models.driver_profile import DriverProfile
from app.db.models.vehicle import Vehicle
from app.db.session import engine

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

def login_tokens(client: TestClient, email: str, password: str = DEFAULT_PASSWORD) -> dict:
    response = login(client, email=email, password=password)
    assert response.status_code == 200, response.text
    return response.json()


def driver_payload(
    *,
    license_number: str = "RJ1420110012345",
    registration_number: str = "RJ14 CD 1234",
    **vehicle_overrides,
) -> dict:
    vehicle = {
        "registration_number": registration_number,
        "make": "Maruti",
        "model": "Dzire",
        "color": "White",
        "vehicle_type": "SEDAN",
    }
    vehicle.update(vehicle_overrides)
    return {"license_number": license_number, "vehicle": vehicle}


def onboard_driver(client: TestClient, n: int = 1) -> tuple[dict, dict]:
    """Register a driver, log in, and submit an application. Returns (tokens, profile)."""
    email = f"driver{n}@example.com"
    assert register(client, email=email, full_name=f"Driver {n}", role="DRIVER").status_code == 201
    tokens = login_tokens(client, email)
    response = client.post(
        "/api/v1/drivers/me",
        json=driver_payload(
            license_number=f"RJ14201100123{n:02d}", registration_number=f"RJ14CD{n:04d}"
        ),
        headers=auth_header(tokens["access_token"]),
    )
    assert response.status_code == 201, response.text
    return tokens, response.json()


def admin_tokens(client: TestClient, email: str = "admin@example.com") -> dict:
    create_user_in_db(email=email, role="ADMIN")
    return login_tokens(client, email)


def review(client: TestClient, admin: dict, driver_id: str, status: str = "APPROVED", reason=None):
    body: dict = {"status": status}
    if reason is not None:
        body["reason"] = reason
    return client.patch(
        f"/api/v1/admin/drivers/{driver_id}/approval",
        json=body,
        headers=auth_header(admin["access_token"]),
    )


def set_availability(client: TestClient, tokens: dict, value: str):
    return client.patch(
        "/api/v1/drivers/me/availability",
        json={"availability": value},
        headers=auth_header(tokens["access_token"]),
    )


def get_my_driver(client: TestClient, tokens: dict):
    return client.get("/api/v1/drivers/me", headers=auth_header(tokens["access_token"]))


def create_driver_in_db(
    *, email: str, verification_status: str = "PENDING", availability: str = "OFFLINE"
) -> uuid.UUID:
    
    user_id = create_user_in_db(email=email, role="DRIVER")
    with SessionLocal() as db:
        profile = DriverProfile(
            user_id=user_id,
            license_number="RJ1420110099999",
            verification_status=verification_status,
            availability=availability,
        )
        db.add(profile)
        db.commit()
        return profile.id


def make_vehicle(profile_id: uuid.UUID, plate: str, *, active: bool = True) -> Vehicle:
    return Vehicle(
        driver_id=profile_id,
        registration_number=plate,
        make="Maruti",
        model="Dzire",
        color="White",
        vehicle_type="SEDAN",
        is_active=active,
    )


def set_active_ride_in_db(profile_id: str | uuid.UUID) -> None:
    with SessionLocal() as db:
        db.execute(
            text("UPDATE driver_profiles SET active_ride_id = :ride WHERE id = :pid"),
            {"ride": uuid.uuid4(), "pid": profile_id},
        )
        db.commit()


@contextmanager
def count_queries():
    statements: list[str] = []

    def _before(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement)

    event.listen(engine, "before_cursor_execute", _before)
    try:
        yield statements
    finally:
        event.remove(engine, "before_cursor_execute", _before)