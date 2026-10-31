import logging
import uuid
from datetime import datetime, timedelta

from sqlalchemy import cast, select, update
from sqlalchemy.dialects.postgresql import CITEXT
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.clock import utcnow
from app.core.config import get_settings
from app.core.exceptions import ConflictError, ForbiddenError, UnauthorizedError
from app.core.security import (
    DUMMY_PASSWORD_HASH,
    create_access_token,
    generate_refresh_token,
    hash_password,
    hash_refresh_token,
    verify_password,
)
from app.db.models.refresh_token import RefreshToken
from app.db.models.user import User
from app.schemas.auth import RegisterRequest, TokenResponse

logger = logging.getLogger(__name__)


def register_user(db: Session, data: RegisterRequest) -> User:
    user = User(
        email=data.email,
        password_hash=hash_password(data.password),
        full_name=data.full_name,
        phone=data.phone,
        role=data.role,
    )
    db.add(user)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        constraint = getattr(getattr(exc.orig, "diag", None), "constraint_name", None)
        if constraint == "uq_users_email":
            raise ConflictError("Email is already registered") from exc
        raise
    db.refresh(user)
    return user


def authenticate(db: Session, email: str, password: str) -> User:
    # Explicit CAST keeps the comparison citext-vs-citext (case-insensitive, index-friendly).
    user = db.execute(
        select(User).where(User.email == cast(email, CITEXT))
    ).scalar_one_or_none()

    # Always run exactly one Argon2 verification, even for unknown emails.
    password_ok = verify_password(password, user.password_hash if user else DUMMY_PASSWORD_HASH)

    if user is None or not password_ok:
        raise UnauthorizedError("Invalid email or password")
    if not user.is_active:
        raise ForbiddenError("Account is disabled")
    return user


def login(db: Session, email: str, password: str) -> TokenResponse:
    user = authenticate(db, email, password)
    raw_refresh, row = _new_refresh_row(user.id, family_id=uuid.uuid4())
    db.add(row)
    db.commit()
    return _token_response(user.id, raw_refresh)


def refresh_tokens(db: Session, raw_token: str) -> TokenResponse:
    """Rotate: revoke the presented refresh token and issue a new one in the same family."""
    now = utcnow()
    # FOR UPDATE serializes two simultaneous refreshes of the same token:
    # the second waits, then sees revoked_at already set.
    row = db.execute(
        select(RefreshToken)
        .where(RefreshToken.token_hash == hash_refresh_token(raw_token))
        .with_for_update()
    ).scalar_one_or_none()

    if row is None:
        raise UnauthorizedError("Invalid refresh token")

    if row.revoked_at is not None:
        # A revoked token came back: it was copied, or the client is replaying.
        # Kill the entire session family and persist that BEFORE raising.
        _revoke_family(db, row.family_id, now)
        db.commit()
        logger.warning(
            "refresh token reuse detected user_id=%s family_id=%s", row.user_id, row.family_id
        )
        raise UnauthorizedError("Invalid refresh token")

    if row.expires_at <= now:
        raise UnauthorizedError("Refresh token expired")

    user = db.get(User, row.user_id)
    if user is None or not user.is_active:
        raise UnauthorizedError("Invalid refresh token")

    raw_new, new_row = _new_refresh_row(user.id, family_id=row.family_id)
    db.add(new_row)
    db.flush()  # assigns new_row.id
    row.revoked_at = now
    row.replaced_by_id = new_row.id
    db.commit()
    return _token_response(user.id, raw_new)


def logout(db: Session, raw_token: str) -> None:
    row = db.execute(
        select(RefreshToken).where(RefreshToken.token_hash == hash_refresh_token(raw_token))
    ).scalar_one_or_none()
    if row is not None:
        _revoke_family(db, row.family_id, utcnow())
        db.commit()


# --- helpers ----------------------------------------------------------------
def _new_refresh_row(user_id: uuid.UUID, family_id: uuid.UUID) -> tuple[str, RefreshToken]:
    settings = get_settings()
    raw = generate_refresh_token()
    row = RefreshToken(
        user_id=user_id,
        token_hash=hash_refresh_token(raw),
        family_id=family_id,
        expires_at=utcnow() + timedelta(days=settings.refresh_token_expire_days),
    )
    return raw, row


def _revoke_family(db: Session, family_id: uuid.UUID, now: datetime) -> None:
    db.execute(
        update(RefreshToken)
        .where(RefreshToken.family_id == family_id, RefreshToken.revoked_at.is_(None))
        .values(revoked_at=now)
    )


def _token_response(user_id: uuid.UUID, raw_refresh: str) -> TokenResponse:
    settings = get_settings()
    return TokenResponse(
        access_token=create_access_token(user_id),
        refresh_token=raw_refresh,
        expires_in=settings.access_token_expire_minutes * 60,
    )