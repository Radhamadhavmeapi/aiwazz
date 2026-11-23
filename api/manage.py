"""Admin CLI. Run from /www/aiwazz/api:  .venv/bin/python manage.py <command> [options]

  create-user  --email E [--role admin|user]   prompts for the password (never pass it as an argument)
  set-password --email E                       prompts for the new password; signs the user out everywhere
  set-active   --email E --active yes|no       disable/enable an account (disabling signs them out)
  list-users
  create-invite [--uses N] [--role user|admin] [--days D] [--label TEXT]   prints the code once
  list-invites
  revoke-invite --id N
"""
import argparse
import asyncio
import getpass
import sys
from datetime import timedelta

from sqlalchemy import delete, select

import models  # noqa: F401
from auth.security import hash_password, new_invite_code, normalize_invite, password_problem, sha256
from db import make_engine, make_sessionmaker, utcnow
from models import ROLES, Invite, User, UserSession
from settings import get_settings


def ask_password(email: str) -> str:
    s = get_settings()
    for _ in range(3):
        pw = getpass.getpass("Password: ")
        if problem := password_problem(pw, email, s.password_min_length):
            print(f"  {problem}")
            continue
        if getpass.getpass("Repeat password: ") != pw:
            print("  Passwords don't match")
            continue
        return pw
    sys.exit("Aborted")


async def main(argv: list[str]) -> None:
    ap = argparse.ArgumentParser(prog="manage.py", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("create-user"); p.add_argument("--email", required=True); p.add_argument("--role", choices=ROLES, default="user")
    p = sub.add_parser("set-password"); p.add_argument("--email", required=True)
    p = sub.add_parser("set-active"); p.add_argument("--email", required=True); p.add_argument("--active", choices=("yes", "no"), required=True)
    sub.add_parser("list-users")
    p = sub.add_parser("create-invite")
    p.add_argument("--uses", type=int, default=1); p.add_argument("--role", choices=ROLES, default="user")
    p.add_argument("--days", type=int, default=14); p.add_argument("--label", default="")
    sub.add_parser("list-invites")
    p = sub.add_parser("revoke-invite"); p.add_argument("--id", type=int, required=True)
    a = ap.parse_args(argv)

    engine = make_engine(get_settings().database_url)
    async with make_sessionmaker(engine)() as db:
        if a.cmd == "create-user":
            email = a.email.lower().strip()
            if (await db.execute(select(User).where(User.email == email))).scalar_one_or_none():
                sys.exit(f"User {email} already exists")
            db.add(User(email=email, password_hash=hash_password(ask_password(email)), role=a.role))
            await db.commit()
            print(f"Created {a.role} {email}")

        elif a.cmd in ("set-password", "set-active"):
            email = a.email.lower().strip()
            user = (await db.execute(select(User).where(User.email == email))).scalar_one_or_none()
            if not user:
                sys.exit(f"No user {email}")
            if a.cmd == "set-password":
                user.password_hash = hash_password(ask_password(email))
            else:
                user.is_active = a.active == "yes"
            if a.cmd == "set-password" or not user.is_active:
                await db.execute(delete(UserSession).where(UserSession.user_id == user.id))
            await db.commit()
            print(f"Updated {email} (active={user.is_active})")

        elif a.cmd == "list-users":
            for u in (await db.execute(select(User).order_by(User.id))).scalars():
                print(f"{u.id:>4}  {u.role:<5}  {'active  ' if u.is_active else 'DISABLED'}  {u.email}  last login: {u.last_login_at or '-'}")

        elif a.cmd == "create-invite":
            code = new_invite_code()
            db.add(Invite(code_hash=sha256(normalize_invite(code)), label=a.label, role=a.role, max_uses=max(1, a.uses),
                          expires_at=utcnow() + timedelta(days=a.days) if a.days > 0 else None))
            await db.commit()
            print(f"Invite code: {code}   (role={a.role}, uses={a.uses}, expires in {a.days} days; shown only now)")

        elif a.cmd == "list-invites":
            now = utcnow()
            for i in (await db.execute(select(Invite).order_by(Invite.id))).scalars():
                state = "revoked" if i.revoked else "expired" if i.expires_at and i.expires_at <= now else "used up" if i.uses >= i.max_uses else "open"
                print(f"{i.id:>4}  {state:<8} {i.uses}/{i.max_uses} uses  role={i.role:<5} expires={i.expires_at or 'never'}  {i.label}")

        elif a.cmd == "revoke-invite":
            inv = await db.get(Invite, a.id)
            if not inv:
                sys.exit("No such invite")
            inv.revoked = True
            await db.commit()
            print(f"Revoked invite {a.id}")
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1:]))
