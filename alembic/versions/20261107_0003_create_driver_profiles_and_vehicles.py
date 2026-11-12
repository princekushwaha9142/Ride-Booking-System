import sqlalchemy as sa
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "driver_profiles",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("license_number", sa.String(length=20), nullable=False),
        sa.Column("verification_status", sa.String(length=20), server_default="PENDING", nullable=False),
        sa.Column("availability", sa.String(length=20), server_default="OFFLINE", nullable=False),
        sa.Column("active_ride_id", sa.Uuid(), nullable=True),
        sa.Column("reviewed_by_id", sa.Uuid(), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("rejection_reason", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint(
            "verification_status IN ('PENDING','APPROVED','REJECTED')",
            name=op.f("ck_driver_profiles_verification_status_valid"),
        ),
        sa.CheckConstraint(
            "availability IN ('OFFLINE','ONLINE')",
            name=op.f("ck_driver_profiles_availability_valid"),
        ),
        sa.CheckConstraint(
            "availability = 'OFFLINE' OR verification_status = 'APPROVED'",
            name=op.f("ck_driver_profiles_online_requires_approval"),
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"],
            name=op.f("fk_driver_profiles_user_id_users"), ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["reviewed_by_id"], ["users.id"],
            name=op.f("fk_driver_profiles_reviewed_by_id_users"), ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_driver_profiles")),
        sa.UniqueConstraint("user_id", name=op.f("uq_driver_profiles_user_id")),
        sa.UniqueConstraint("license_number", name=op.f("uq_driver_profiles_license_number")),
    )
    op.create_index(
        "ix_driver_profiles_status_created",
        "driver_profiles",
        ["verification_status", "created_at"],
    )

    op.create_table(
        "vehicles",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("driver_id", sa.Uuid(), nullable=False),
        sa.Column("registration_number", sa.String(length=20), nullable=False),
        sa.Column("make", sa.String(length=50), nullable=False),
        sa.Column("model", sa.String(length=50), nullable=False),
        sa.Column("color", sa.String(length=30), nullable=False),
        sa.Column("vehicle_type", sa.String(length=20), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint(
            "vehicle_type IN ('AUTO','BIKE','HATCHBACK','SEDAN','SUV')",
            name=op.f("ck_vehicles_vehicle_type_valid"),
        ),
        sa.ForeignKeyConstraint(
            ["driver_id"], ["driver_profiles.id"],
            name=op.f("fk_vehicles_driver_id_driver_profiles"), ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_vehicles")),
        sa.UniqueConstraint("registration_number", name=op.f("uq_vehicles_registration_number")),
    )
    op.create_index(op.f("ix_vehicles_driver_id"), "vehicles", ["driver_id"])
    op.create_index(
        "uq_vehicles_one_active_per_driver",
        "vehicles",
        ["driver_id"],
        unique=True,
        postgresql_where=sa.text("is_active"),
    )


def downgrade() -> None:
    op.drop_table("vehicles")  # its indexes go with it
    op.drop_table("driver_profiles")