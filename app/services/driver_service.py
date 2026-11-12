import uuid

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.core.exceptions import ConflictError, ForbiddenError, NotFoundError
from app.db.models.driver_profile import Availability, DriverProfile, VerificationStatus
from app.db.models.user import User
from app.db.models.vehicle import Vehicle
from app.db.utils import violated_constraint
from app.schemas.driver import DriverCreate, DriverUpdate

_CONFLICT_MESSAGES = {
    "uq_driver_profiles_user_id": "Driver profile already exists",
    "uq_driver_profiles_license_number": "License number is already registered",
    "uq_vehicles_registration_number": "Vehicle registration number is already registered",
}


def _raise_if_known_conflict(exc: IntegrityError) -> None:
    message = _CONFLICT_MESSAGES.get(violated_constraint(exc) or "")
    if message:
        raise ConflictError(message) from exc


def _select_profile(*where, lock: bool = False):
    stmt = (
        select(DriverProfile)
        .where(*where)
        # selectinload = separate queries, so FOR UPDATE never touches an outer join.
        .options(selectinload(DriverProfile.vehicles), selectinload(DriverProfile.user))
    )
    return stmt.with_for_update() if lock else stmt


def _get_for_update(db: Session, user_id: uuid.UUID) -> DriverProfile:
    """Load the driver's row and lock it until this transaction ends."""
    profile = db.execute(
        _select_profile(DriverProfile.user_id == user_id, lock=True)
    ).scalar_one_or_none()
    if profile is None:
        raise NotFoundError("Driver profile not found")
    return profile


def _reload(db: Session, profile_id: uuid.UUID) -> DriverProfile:
    return db.execute(
        _select_profile(DriverProfile.id == profile_id).execution_options(populate_existing=True)
    ).scalar_one()


def get_driver_profile(db: Session, user_id: uuid.UUID) -> DriverProfile:
    profile = db.execute(_select_profile(DriverProfile.user_id == user_id)).scalar_one_or_none()
    if profile is None:
        raise NotFoundError("Driver profile not found")
    return profile


def create_driver_profile(db: Session, user: User, data: DriverCreate) -> DriverProfile:
    """Submit an application: profile + vehicle in ONE transaction (all or nothing)."""
    profile = DriverProfile(user_id=user.id, license_number=data.license_number)
    profile.vehicles.append(Vehicle(**data.vehicle.model_dump()))
    db.add(profile)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        _raise_if_known_conflict(exc)
        raise
    return _reload(db, profile.id)


def update_driver_profile(db: Session, user: User, data: DriverUpdate) -> DriverProfile:
    profile = _get_for_update(db, user.id)
    if profile.active_ride_id is not None:
        raise ConflictError("Cannot change profile details during an active ride")

    needs_reverification = False

    if data.license_number is not None and data.license_number != profile.license_number:
        profile.license_number = data.license_number
        needs_reverification = True

    if data.vehicle is not None:
        vehicle = profile.vehicle
        if vehicle is None:
            raise ConflictError("No active vehicle to update")
        changes = data.vehicle.model_dump(exclude_none=True)
        if changes.get("registration_number", vehicle.registration_number) != vehicle.registration_number:
            needs_reverification = True
        for field, value in changes.items():
            setattr(vehicle, field, value)

    if needs_reverification:
        # Approval was granted for the old details. Start over, and go offline
        # (the CHECK constraint would reject PENDING + ONLINE anyway).
        profile.verification_status = VerificationStatus.PENDING.value
        profile.availability = Availability.OFFLINE.value
        profile.reviewed_by_id = None
        profile.reviewed_at = None
        profile.rejection_reason = None

    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        _raise_if_known_conflict(exc)
        raise
    return _reload(db, profile.id)


def set_availability(db: Session, user: User, target: str) -> DriverProfile:
    # The row lock serializes this against an admin revoking approval at the same moment.
    profile = _get_for_update(db, user.id)

    if profile.availability == target:  # idempotent: nothing to change
        db.rollback()  # release the row lock
        return profile

    if target == Availability.ONLINE.value:
        if profile.verification_status != VerificationStatus.APPROVED.value:
            raise ForbiddenError("Driver account is not approved yet")
        if profile.vehicle is None:
            raise ConflictError("An active vehicle is required to go online")
    elif profile.active_ride_id is not None:
        raise ConflictError("Cannot go offline during an active ride")

    profile.availability = target
    db.commit()
    return _reload(db, profile.id)