import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import get_db, require_roles
from app.db.models.driver_profile import DriverProfile, VerificationStatus
from app.db.models.user import Role, User
from app.schemas.common import Page
from app.schemas.driver import ApprovalUpdate, DriverAdminResponse
from app.schemas.user import UserResponse
from app.services import admin_service

router = APIRouter(prefix="/admin", tags=["admin"])
admin_only = require_roles(Role.ADMIN)


@router.get("/users", response_model=Page[UserResponse])
def list_users(
    role: Role | None = None,
    is_active: bool | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    _admin: User = Depends(admin_only),
) -> dict:
    items, total = admin_service.list_users(
        db, role=role, is_active=is_active, page=page, page_size=page_size
    )
    return {"items": items, "total": total, "page": page, "page_size": page_size}


@router.get("/drivers/pending", response_model=Page[DriverAdminResponse])
def list_pending_drivers(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    _admin: User = Depends(admin_only),
) -> dict:
    items, total = admin_service.list_drivers(
        db, status=VerificationStatus.PENDING, page=page, page_size=page_size
    )
    return {"items": items, "total": total, "page": page, "page_size": page_size}


@router.patch("/drivers/{driver_id}/approval", response_model=DriverAdminResponse)
def review_driver(
    driver_id: uuid.UUID,
    payload: ApprovalUpdate,
    db: Session = Depends(get_db),
    admin: User = Depends(admin_only),
) -> DriverProfile:
    return admin_service.review_driver(db, admin, driver_id, payload.status, payload.reason)