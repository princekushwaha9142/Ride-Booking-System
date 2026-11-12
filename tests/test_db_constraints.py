import pytest
from sqlalchemy.exc import IntegrityError

from app.db.models.user import User
from app.db.session import SessionLocal
from tests.helpers import create_driver_in_db, make_vehicle


def _user(email: str, role: str = "RIDER") -> User:
    return User(email=email, password_hash="hash", full_name="X", role=role)


def test_check_constraint_rejects_unknown_role() -> None:
    with SessionLocal() as db:
        db.add(_user("a@example.com", role="HACKER"))
        with pytest.raises(IntegrityError):
            db.commit()


def test_unique_constraint_is_case_insensitive() -> None:
    with SessionLocal() as db:
        db.add(_user("a@example.com"))
        db.commit()
    with SessionLocal() as db:
        db.add(_user("A@Example.com"))
        with pytest.raises(IntegrityError):
            db.commit()

def test_unapproved_driver_cannot_be_online_at_database_level() -> None:
    with pytest.raises(IntegrityError):
        create_driver_in_db(
            email="d@example.com", verification_status="PENDING", availability="ONLINE"
        )


def test_approved_driver_can_be_online_at_database_level() -> None:
    create_driver_in_db(
        email="d@example.com", verification_status="APPROVED", availability="ONLINE"
    )


def test_unknown_verification_status_is_rejected_by_database() -> None:
    with pytest.raises(IntegrityError):
        create_driver_in_db(email="d@example.com", verification_status="MAYBE")


def test_only_one_active_vehicle_per_driver() -> None:
    profile_id = create_driver_in_db(email="d@example.com")
    with SessionLocal() as db:
        db.add(make_vehicle(profile_id, "AAA1111"))
        db.commit()

    with SessionLocal() as db:
        db.add(make_vehicle(profile_id, "BBB2222"))
        with pytest.raises(IntegrityError):
            db.commit()

    with SessionLocal() as db:  # an inactive second vehicle is fine
        db.add(make_vehicle(profile_id, "CCC3333", active=False))
        db.commit()