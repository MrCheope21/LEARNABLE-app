"""Administer accounts from the server's command line.

    python scripts/manage_users.py list
    python scripts/manage_users.py admin --email me@example.com            # make administrator
    python scripts/manage_users.py admin --email me@example.com --remove
    python scripts/manage_users.py suspend --email x@example.com [--undo]
    python scripts/manage_users.py delete --email-domain example.com [--yes]   # test accounts
    python scripts/manage_users.py delete --email x@example.com [--yes]

`delete` removes the accounts and ALL their data, files included; without --yes it only lists
what it would delete. Uses the configured DATABASE_URL and storage (.env), like the server.
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import func, select

import app.models  # noqa: F401  (registers every model)
from app.db.session import get_session_factory
from app.models.course import Course
from app.models.user import User
from app.services import accounts
from app.storage.documents import get_document_storage


def _find(db, args) -> list[User]:
    if getattr(args, "email", None):
        found = db.scalars(select(User).where(User.email == args.email.strip().lower())).all()
    elif getattr(args, "email_domain", None):
        domain = "@" + args.email_domain.strip().lower().lstrip("@")
        found = db.scalars(select(User).where(User.email.like(f"%{domain}"))).all()
    else:
        found = []
    return list(found)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("list")
    admin = sub.add_parser("admin")
    admin.add_argument("--email", required=True)
    admin.add_argument("--remove", action="store_true")
    suspend = sub.add_parser("suspend")
    suspend.add_argument("--email", required=True)
    suspend.add_argument("--undo", action="store_true")
    delete = sub.add_parser("delete")
    delete.add_argument("--email")
    delete.add_argument("--email-domain")
    delete.add_argument("--yes", action="store_true")
    args = parser.parse_args()

    with get_session_factory()() as db:
        if args.command == "list":
            courses = dict(
                db.execute(select(Course.user_id, func.count()).group_by(Course.user_id)).all()
            )
            for user in db.scalars(select(User).order_by(User.created_at)).all():
                flags = ("admin " if user.is_admin else "") + (
                    "" if user.is_active else "SUSPENDED"
                )
                print(f"{user.email:40} {courses.get(user.id, 0):4} courses  {flags}")
            return 0
        users = _find(db, args)
        if not users:
            print("No matching account.", file=sys.stderr)
            return 2
        if args.command == "admin":
            users[0].is_admin = not args.remove
            db.commit()
            print(f"{users[0].email}: administrator = {users[0].is_admin}")
        elif args.command == "suspend":
            accounts.set_active(db, users[0].id, args.undo)
            print(f"{users[0].email}: active = {args.undo}")
        elif args.command == "delete":
            if not (args.email or args.email_domain):
                print("Give --email or --email-domain.", file=sys.stderr)
                return 2
            print(f"{len(users)} account(s) matched.")
            if not args.yes:
                for user in users[:20]:
                    print("  ", user.email)
                print("Nothing deleted. Repeat with --yes to delete them and all their data.")
                return 0
            storage = get_document_storage()
            for user in users:
                accounts.delete_account(db, storage, user.id)
            print("Deleted.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
