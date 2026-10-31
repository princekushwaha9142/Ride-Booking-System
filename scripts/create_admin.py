
import argparse
import getpass
import sys

from sqlalchemy.exc import IntegrityError

from app.core.security import hash_password
from app.db.models.user import Role, User
from app.db.session import SessionLocal


def main() -> None:
    parser = argparse.ArgumentParser(description="Create an admin user")
    parser.add_argument("email")
    parser.add_argument("full_name")
    args = parser.parse_args()

    # getpass keeps the password out of your shell history.
    password = getpass.getpass("Password (min 8 chars): ")
    if len(password) < 8 or password != getpass.getpass("Repeat password: "):
        sys.exit("Passwords must match and be at least 8 characters.")

    with SessionLocal() as db:
        user = User(
            email=args.email,
            password_hash=hash_password(password),
            full_name=args.full_name,
            role=Role.ADMIN.value,
        )
        db.add(user)
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            sys.exit("A user with that email already exists.")
        print(f"Admin created: {user.id}")


if __name__ == "__main__":
    main()