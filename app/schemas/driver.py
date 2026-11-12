import re
import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.db.models.driver_profile import Availability, VerificationStatus
from app.schemas.user import UserResponse

VehicleType = Literal["AUTO", "BIKE", "HATCHBACK", "SEDAN", "SUV"]

_PLATE_RE = re.compile(r"^[A-Z0-9]{4,12}$")
_LICENSE_RE = re.compile(r"^[A-Z0-9]{8,20}$")


def _canonical(value: str) -> str:
    """Uppercase and drop spaces/hyphens so formatting can't bypass uniqueness."""
    return re.sub(r"[\s-]", "", value).upper()


def normalize_plate(value: str) -> str:
    value = _canonical(value)
    if not _PLATE_RE.match(value):
        raise ValueError("registration number must be 4-12 letters/digits")
    return value


def normalize_license(value: str) -> str:
    value = _canonical(value)
    if not _LICENSE_RE.match(value):
        raise ValueError("license number must be 8-20 letters/digits")
    return value


def _clean_text(value: str) -> str:
    value = value.strip()
    if not value:
        raise ValueError("must not be blank")
    return value


# --- Requests ----------------------------------------------------------------
class VehicleIn(BaseModel):
    registration_number: str = Field(min_length=4, max_length=20)
    make: str = Field(min_length=1, max_length=50)
    model: str = Field(min_length=1, max_length=50)
    color: str = Field(min_length=1, max_length=30)
    vehicle_type: VehicleType

    @field_validator("registration_number")
    @classmethod
    def _plate(cls, value: str) -> str:
        return normalize_plate(value)

    @field_validator("make", "model", "color")
    @classmethod
    def _text(cls, value: str) -> str:
        return _clean_text(value)


class VehicleUpdate(BaseModel):

    registration_number: str | None = Field(default=None, min_length=4, max_length=20)
    make: str | None = Field(default=None, min_length=1, max_length=50)
    model: str | None = Field(default=None, min_length=1, max_length=50)
    color: str | None = Field(default=None, min_length=1, max_length=30)
    vehicle_type: VehicleType | None = None

    @field_validator("registration_number")
    @classmethod
    def _plate(cls, value: str | None) -> str | None:
        return None if value is None else normalize_plate(value)

    @field_validator("make", "model", "color")
    @classmethod
    def _text(cls, value: str | None) -> str | None:
        return None if value is None else _clean_text(value)

    @model_validator(mode="after")
    def _not_empty(self) -> "VehicleUpdate":
        if not self.model_dump(exclude_none=True):
            raise ValueError("provide at least one vehicle field to update")
        return self


class DriverCreate(BaseModel):
    license_number: str = Field(min_length=8, max_length=30)
    vehicle: VehicleIn

    @field_validator("license_number")
    @classmethod
    def _license(cls, value: str) -> str:
        return normalize_license(value)


class DriverUpdate(BaseModel):
    license_number: str | None = Field(default=None, min_length=8, max_length=30)
    vehicle: VehicleUpdate | None = None

    @field_validator("license_number")
    @classmethod
    def _license(cls, value: str | None) -> str | None:
        return None if value is None else normalize_license(value)

    @model_validator(mode="after")
    def _not_empty(self) -> "DriverUpdate":
        if self.license_number is None and self.vehicle is None:
            raise ValueError("provide at least one field to update")
        return self


class AvailabilityUpdate(BaseModel):
    availability: Literal["ONLINE", "OFFLINE"]


class ApprovalUpdate(BaseModel):
    status: Literal["APPROVED", "REJECTED"]
    reason: str | None = Field(default=None, max_length=500)

    @model_validator(mode="after")
    def _reason_rules(self) -> "ApprovalUpdate":
        if self.status == "REJECTED":
            if not (self.reason and self.reason.strip()):
                raise ValueError("reason is required when rejecting a driver")
            self.reason = self.reason.strip()
        else:
            self.reason = None
        return self


# --- Responses ---------------------------------------------------------------
class VehicleResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    registration_number: str
    make: str
    model: str
    color: str
    vehicle_type: VehicleType
    is_active: bool


class DriverResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID
    license_number: str
    verification_status: VerificationStatus
    availability: Availability
    rejection_reason: str | None
    reviewed_at: datetime | None
    vehicle: VehicleResponse | None  # read from DriverProfile.vehicle
    created_at: datetime


class DriverAdminResponse(DriverResponse):
    reviewed_by_id: uuid.UUID | None
    user: UserResponse