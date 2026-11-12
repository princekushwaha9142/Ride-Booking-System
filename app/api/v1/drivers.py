from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.api.deps import get_db, require_roles
from app.db.models.driver_profile import DriverProfile
from app.db.models.user import Role, User
from app.schemas.driver import AvailabilityUpdate, DriverCreate, DriverResponse, DriverUpdate
from app.services import driver_service

router = APIRouter(prefix="/drivers", tags=["drivers"])
driver_only = require_roles(Role.DRIVER)


@router.post("/me", response_model=DriverResponse, status_code=status.HTTP_201_CREATED)
def submit_application(
    payload: DriverCreate, db: Session = Depends(get_db), user: User = Depends(driver_only)
) -> DriverProfile:
    return driver_service.create_driver_profile(db, user, payload)


@router.get("/me", response_model=DriverResponse)
def read_my_profile(
    db: Session = Depends(get_db), user: User = Depends(driver_only)
) -> DriverProfile:
    return driver_service.get_driver_profile(db, user.id)


@router.patch("/me", response_model=DriverResponse)
def update_my_profile(
    payload: DriverUpdate, db: Session = Depends(get_db), user: User = Depends(driver_only)
) -> DriverProfile:
    return driver_service.update_driver_profile(db, user, payload)


@router.patch("/me/availability", response_model=DriverResponse)
def update_my_availability(
    payload: AvailabilityUpdate, db: Session = Depends(get_db), user: User = Depends(driver_only)
) -> DriverProfile:
    return driver_service.set_availability(db, user, payload.availability)