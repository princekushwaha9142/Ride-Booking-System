# Import every model module here so Alembic's autogenerate and SQLAlchemy's
# string-based relationships can see all of them.
from app.db.models.driver_profile import Availability, DriverProfile, VerificationStatus  # noqa: F401
from app.db.models.refresh_token import RefreshToken  # noqa: F401
from app.db.models.user import Role, User  # noqa: F401
from app.db.models.vehicle import Vehicle  # noqa: F401