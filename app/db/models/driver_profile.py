import enum
import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.db.models.user import User
    from app.db.models.vehicle import Vehicle


class VerificationStatus(str, enum.Enum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


class Availability(str, enum.Enum):
    OFFLINE = "OFFLINE"
    ONLINE = "ONLINE"


class DriverProfile(Base, TimestampMixin):
    __tablename__ = "driver_profiles"
    __table_args__ = (
        CheckConstraint(
            "verification_status IN ('PENDING','APPROVED','REJECTED')",
            name="verification_status_valid",
        ),
        CheckConstraint("availability IN ('OFFLINE','ONLINE')", name="availability_valid"),
        # The core invariant: only approved drivers can ever be ONLINE.
        CheckConstraint(
            "availability = 'OFFLINE' OR verification_status = 'APPROVED'",
            name="online_requires_approval",
        ),
        Index("ix_driver_profiles_status_created", "verification_status", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    license_number: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)
    verification_status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default=VerificationStatus.PENDING.value,
        server_default=VerificationStatus.PENDING.value,
    )
    availability: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default=Availability.OFFLINE.value,
        server_default=Availability.OFFLINE.value,
    )
    # No foreign key yet: the rides table arrives in Phase 5 (FK added there).
    active_ride_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True)

    reviewed_by_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    rejection_reason: Mapped[str | None] = mapped_column(Text)

    # Two FKs point at users (owner and reviewer), so we say which one this uses.
    user: Mapped["User"] = relationship(foreign_keys="DriverProfile.user_id")
    vehicles: Mapped[list["Vehicle"]] = relationship(
        back_populates="driver", order_by="Vehicle.created_at"
    )

    @property
    def vehicle(self) -> "Vehicle | None":
        """The single active vehicle (uses the loaded collection, no extra query)."""
        return next((v for v in self.vehicles if v.is_active), None)