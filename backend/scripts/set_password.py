"""Sets a new password for an account (administration; there is no way to read one back).

    cd backend
    .venv/bin/python scripts/set_password.py --email someone@example.com
    .venv/bin/python scripts/set_password.py --email someone@example.com --password "..."

Without --password a random one is generated and printed once. Every existing session of the
account ends. Uses the configured DATABASE_URL (.env), like the server.
"""

import argparse
import secrets
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select

import app.models  # noqa: F401  (registers every model)
from app.auth.passwords import set_password
from app.db.session import get_session_factory
from app.models.user import User

MIN_LENGTH = 12


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--email", required=True)
    parser.add_argument("--password", help=f"at least {MIN_LENGTH} characters; omit to generate")
    args = parser.parse_args()
    password = args.password or secrets.token_urlsafe(12)
    if len(password) < MIN_LENGTH:
        print(f"Use at least {MIN_LENGTH} characters.", file=sys.stderr)
        return 2
    with get_session_factory()() as db:
        user = db.scalar(select(User).where(User.email == args.email.strip().lower()))
        if user is None:
            print(f"No account for {args.email}.", file=sys.stderr)
            return 1
        email = user.email
        set_password(db, user, password)
        db.commit()
    print(f"New password for {email}: {password}")
    print("Every existing session of this account has been signed out.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
