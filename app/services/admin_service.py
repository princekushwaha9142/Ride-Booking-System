import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload, selectinload

from app.core.clock import utcnow
from app.core.exceptions import ConflictError, NotFoundError
from app.db.models.driver_profile import Availability, DriverProfile, VerificationStatus
from app.db.models.user import Role, User
from app.services.driver_service import _reload, _select_profile


def list_users(
    db: Session, *, role: Role | None, is_active: bool | None, page: int, page_size: int
) -> tuple[list[User], int]:
    filters = []
    if role is not None:
        filters.append(User.role == role.value)
    if is_active is not None:
        filters.append(User.is_active == is_active)

    total = db.execute(select(func.count()).select_from(User).where(*filters)).scalar_one()
    items = (
        db.execute(
            select(User)
            .where(*filters)
            .order_by(User.created_at.desc(), User.id)  # id breaks ties => stable pages
            .limit(page_size)
            .offset((page - 1) * page_size)
        )
        .scalars()
        .all()
    )
    return list(items), total


def list_drivers(
    db: Session, *, status: VerificationStatus, page: int, page_size: int
) -> tuple[list[DriverProfile], int]:
    where = DriverProfile.verification_status == status.value
    total = db.execute(
        select(func.count()).select_from(DriverProfile).where(where)
    ).scalar_one()
    items = (
        db.execute(
            select(DriverProfile)
            .where(where)
            # Eager loading: a fixed number of queries no matter how many rows (no N+1).
            .options(joinedload(DriverProfile.user), selectinload(DriverProfile.vehicles))
            .order_by(DriverProfile.created_at, DriverProfile.id)  # oldest application first
            .limit(page_size)
            .offset((page - 1) * page_size)
        )
        .scalars()
        .all()
    )
    return list(items), total


def review_driver(
    db: Session, admin: User, driver_id: uuid.UUID, status: str, reason: str | None
) -> DriverProfile:
    profile = db.execute(_select_profile(DriverProfile.id == driver_id, lock=True)).scalar_one_or_none()
    if profile is None:
        raise NotFoundError("Driver not found")

    if profile.verification_status == status:  # idempotent: already in that state
        db.rollback()  # release the row lock
        return profile

    if status == VerificationStatus.APPROVED.value:
        if profile.vehicle is None:
            raise ConflictError("Driver has no active vehicle")
        profile.rejection_reason = None
    else:
        if profile.active_ride_id is not None:
            raise ConflictError("Driver is on an active ride")
        profile.rejection_reason = reason
        # Revoking approval takes the driver offline in the SAME transaction,
        # otherwise the CHECK constraint would reject the update.
        profile.availability = Availability.OFFLINE.value

    profile.verification_status = status
    profile.reviewed_by_id = admin.id
    profile.reviewed_at = utcnow()
    db.commit()
    return _reload(db, profile.id)