import pytest
from sqlalchemy.exc import IntegrityError

from app.db.models.user import User
from app.db.session import SessionLocal


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