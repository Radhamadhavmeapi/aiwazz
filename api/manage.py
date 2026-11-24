"""Admin CLI. Run from /www/aiwazz/api:  .venv/bin/python manage.py <command> [options]

  create-user  --email E [--role admin|user]   prompts for the password (never pass it as an argument)
  set-password --email E                       prompts for the new password; signs the user out everywhere
  set-active   --email E --active yes|no       disable/enable an account (disabling signs them out)
  list-users
  set-plan     --email E --plan free|starter|creator|pro [--until YYYY-MM-DD]
               --until: the plan ends after that day (India time), then the user is moved back to Free automatically
  expire-plans                                 move ended time-limited plans back to Free now (the API also does this hourly)
  create-invite [--uses N] [--role user|admin] [--days D] [--label TEXT]   prints the code once
  list-invites
  revoke-invite --id N
  list-messages [--all]                        contact form messages (unhandled only unless --all)
  mark-handled --id N
  list-requests [--all]                        "Request an invite" entries (new only unless --all)
  mark-request --id N --status invited|declined|new
  set-secret NAME                              hidden prompt; writes NAME=value into api/.env (chmod 600). Allowed names:
               AIWAZZ_RAZORPAY_KEY_ID, AIWAZZ_RAZORPAY_KEY_SECRET, AIWAZZ_RAZORPAY_WEBHOOK_SECRET, AIWAZZ_SMTP_PASSWORD
  billing-create-plans [--force]               creates the 6 Razorpay plans (3 plans × monthly/yearly) from legal.json
                                               and stores their ids in api/.env (AIWAZZ_RAZORPAY_PLAN_IDS)
  billing-check                                compares the Razorpay plan amounts with legal.json
  list-invoices [--limit N]
  list-pronunciations [--email E]              the global list (or one user's list with --email)
  add-pronunciation --word W --say-as S        add/update a global entry (case-insensitive, whole word)
  remove-pronunciation --word W                remove a global entry
"""
import argparse
import asyncio
import getpass
import sys
from datetime import date, datetime, timedelta

from sqlalchemy import delete, select

import models  # noqa: F401
from auth.security import hash_password, new_invite_code, normalize_invite, password_problem, sha256
from db import make_engine, make_sessionmaker, utcnow
from models import ROLES, Invite, User, UserSession
from settings import get_settings


SECRET_NAMES = ("AIWAZZ_RAZORPAY_KEY_ID", "AIWAZZ_RAZORPAY_KEY_SECRET", "AIWAZZ_RAZORPAY_WEBHOOK_SECRET", "AIWAZZ_SMTP_PASSWORD")
ENV_FILE = __import__("pathlib").Path(__file__).resolve().parent / ".env"


def set_env(name: str, value: str) -> None:
    """Replace or append NAME=value in api/.env, keeping it chmod 600. Values are written single-quoted."""
    import os
    import re
    if "\n" in value or "'" in value:
        sys.exit("Value can't contain newlines or single quotes")
    lines = ENV_FILE.read_text().splitlines() if ENV_FILE.exists() else []
    line = f"{name}='{value}'"
    lines = [line if re.match(rf"^{re.escape(name)}=", ln) else ln for ln in lines]
    if line not in lines:
        lines.append(line)
    ENV_FILE.write_text("\n".join(lines) + "\n")
    os.chmod(ENV_FILE, 0o600)


async def billing_plans(a) -> None:
    import json

    from billing.gst import GST_RATE, PAID_PLANS, PERIODS, charge_paise, plan_prices
    from billing.razorpay import client
    s = get_settings()
    if not (s.razorpay_key_id and s.razorpay_key_secret):
        sys.exit("Set AIWAZZ_RAZORPAY_KEY_ID and AIWAZZ_RAZORPAY_KEY_SECRET first (manage.py set-secret …)")
    rz, prices = client(), plan_prices()
    mode = "TEST" if s.billing_test_mode else "LIVE"
    if a.cmd == "billing-check":
        ok = True
        for key, pid in sorted(s.razorpay_plan_ids.items()):
            plan, period = key.split("_")
            want = charge_paise(plan, period)[1]
            got = (await rz.get_plan(pid))["item"]["amount"]
            ok &= got == want
            print(f"{key:<16} {pid}  Razorpay ₹{got / 100:,.2f}  legal.json ₹{want / 100:,.2f}  {'OK' if got == want else 'MISMATCH'}")
        sys.exit(0 if ok and s.razorpay_plan_ids else 1)
    if s.razorpay_plan_ids and not a.force:
        sys.exit("Plan ids already set (AIWAZZ_RAZORPAY_PLAN_IDS). Use --force to create new ones (e.g. after a price change).")
    ids = {}
    for plan in PAID_PLANS:
        for period in PERIODS:
            base, total = charge_paise(plan, period)
            r = await rz.create_plan(period, total, f"AiWazz {prices[plan]['name']} ({period})",
                                     f"₹{base // 100:,} + {GST_RATE}% GST", {"plan": plan, "period": period})
            ids[f"{plan}_{period}"] = r["id"]
            print(f"[{mode}] {plan}_{period:<8} {r['id']}  ₹{total / 100:,.2f} incl. GST")
    set_env("AIWAZZ_RAZORPAY_PLAN_IDS", json.dumps(ids, separators=(",", ":")))
    print("Saved AIWAZZ_RAZORPAY_PLAN_IDS in api/.env. Restart the API: pm2 restart voice-api")


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
    p = sub.add_parser("set-plan"); p.add_argument("--email", required=True); p.add_argument("--plan", choices=("free", "starter", "creator", "pro"), required=True)
    p.add_argument("--until", type=date.fromisoformat, default=None, help="last day of the plan (YYYY-MM-DD, India time)")
    sub.add_parser("expire-plans")
    p = sub.add_parser("list-requests"); p.add_argument("--all", action="store_true")
    p = sub.add_parser("mark-request"); p.add_argument("--id", type=int, required=True)
    p.add_argument("--status", choices=("new", "invited", "declined"), required=True)
    p = sub.add_parser("create-invite")
    p.add_argument("--uses", type=int, default=1); p.add_argument("--role", choices=ROLES, default="user")
    p.add_argument("--days", type=int, default=14); p.add_argument("--label", default="")
    sub.add_parser("list-invites")
    p = sub.add_parser("revoke-invite"); p.add_argument("--id", type=int, required=True)
    p = sub.add_parser("list-messages"); p.add_argument("--all", action="store_true")
    p = sub.add_parser("mark-handled"); p.add_argument("--id", type=int, required=True)
    p = sub.add_parser("set-secret"); p.add_argument("name", choices=SECRET_NAMES)
    p = sub.add_parser("billing-create-plans"); p.add_argument("--force", action="store_true")
    sub.add_parser("billing-check")
    p = sub.add_parser("list-invoices"); p.add_argument("--limit", type=int, default=30)
    p = sub.add_parser("list-pronunciations"); p.add_argument("--email")
    p = sub.add_parser("add-pronunciation"); p.add_argument("--word", required=True); p.add_argument("--say-as", required=True)
    p = sub.add_parser("remove-pronunciation"); p.add_argument("--word", required=True)
    a = ap.parse_args(argv)
    if a.cmd == "set-secret":
        value = getpass.getpass(f"{a.name} (input hidden): ").strip()
        if not value:
            sys.exit("Nothing entered; .env unchanged")
        set_env(a.name, value)
        print(f"Saved {a.name} in {ENV_FILE} (not shown). Restart the API: pm2 restart voice-api")
        return
    if a.cmd in ("billing-create-plans", "billing-check"):
        await billing_plans(a)
        return

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
                print(f"{u.id:>4}  {u.role:<5}  {u.plan:<7}{(' until ' + format(u.plan_until, '%Y-%m-%d %H:%M') + ' UTC') if u.plan_until else ''}  {'active  ' if u.is_active else 'DISABLED'}  {u.email}  last login: {u.last_login_at or '-'}")

        elif a.cmd == "set-plan":
            u = (await db.execute(select(User).where(User.email == a.email.lower().strip()))).scalar_one_or_none()
            if not u:
                sys.exit(f"No user {a.email}")
            if a.until and a.plan == "free":
                sys.exit("--until only makes sense with a paid plan")
            u.plan = a.plan
            # End of the given day in IST (UTC+5:30), stored as naive UTC
            u.plan_until = (datetime.combine(a.until, datetime.min.time()) + timedelta(days=1, hours=-5, minutes=-30)) if a.until else None
            if u.plan_until and u.plan_until <= utcnow():
                sys.exit("--until is in the past")
            await db.commit()
            print(f"{u.email} is now on the {a.plan} plan" + (f" until the end of {a.until} (India time), then Free" if a.until else ""))

        elif a.cmd == "expire-plans":
            from usage import expire_plans
            print(f"Moved {await expire_plans(db)} user(s) back to Free")

        elif a.cmd == "list-invoices":
            from models import Invoice
            for i in (await db.execute(select(Invoice).order_by(Invoice.id.desc()).limit(a.limit))).scalars():
                tax = f"IGST {i.igst_paise / 100:.2f}" if i.igst_paise else f"CGST+SGST {(i.cgst_paise + i.sgst_paise) / 100:.2f}"
                print(f"{i.number}  {i.issued_at:%Y-%m-%d}  {i.buyer_email}  {i.plan}/{i.period}  "
                      f"taxable {i.taxable_paise / 100:.2f}  {tax}  total {i.total_paise / 100:.2f}")

        elif a.cmd in ("list-pronunciations", "add-pronunciation", "remove-pronunciation"):
            from models import Pronunciation
            from tts.pronounce import check_entry, clean_word
            uid = None
            if getattr(a, "email", None):
                u = (await db.execute(select(User).where(User.email == a.email.lower().strip()))).scalar_one_or_none()
                if not u:
                    sys.exit(f"No user {a.email}")
                uid = u.id
            cond = Pronunciation.user_id.is_(None) if uid is None else Pronunciation.user_id == uid
            if a.cmd == "list-pronunciations":
                for r in (await db.execute(select(Pronunciation).where(cond).order_by(Pronunciation.word_key))).scalars():
                    print(f"{r.id:>5}  {r.word}  →  {r.say_as}")
                print("built in: ₹ → रुपये (Hindi voices) / rupees (English voices)")
            else:
                word = clean_word(a.word)
                row = (await db.execute(select(Pronunciation).where(cond, Pronunciation.word_key == word.lower()))).scalars().first()
                if a.cmd == "remove-pronunciation":
                    if not row:
                        sys.exit(f"No global entry for {word}")
                    await db.delete(row)
                    await db.commit()
                    print(f"Removed {word}")
                else:
                    if msg := check_entry(word, a.say_as):
                        sys.exit(msg)
                    say = " ".join(a.say_as.split())
                    if row:
                        row.word, row.say_as, row.updated_at = word, say, utcnow()
                    else:
                        db.add(Pronunciation(user_id=None, word=word, word_key=word.lower(), say_as=say))
                    await db.commit()
                    print(f"Global: {word} → {say}")

        elif a.cmd == "list-requests":
            from models import InviteRequest
            q = select(InviteRequest).order_by(InviteRequest.id)
            if not a.all:
                q = q.where(InviteRequest.status == "new")
            for r in (await db.execute(q)).scalars():
                print(f"#{r.id} {r.updated_at:%Y-%m-%d %H:%M} UTC  [{r.status}]  {r.email}  {r.name}")
                if r.use_case:
                    print("   " + r.use_case.replace("\n", "\n   "))

        elif a.cmd == "mark-request":
            from models import InviteRequest
            r = await db.get(InviteRequest, a.id)
            if not r:
                sys.exit("No such request")
            r.status = a.status
            await db.commit()
            print(f"Request {a.id} → {a.status}")

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

        elif a.cmd == "list-messages":
            from models import ContactMessage
            q = select(ContactMessage).order_by(ContactMessage.id)
            if not a.all:
                q = q.where(ContactMessage.handled.is_(False))
            for m in (await db.execute(q)).scalars():
                print(f"#{m.id} {m.created_at:%Y-%m-%d %H:%M} UTC  {m.name} <{m.email}>  [{m.subject}]{'  (handled)' if m.handled else ''}")
                print("   " + m.message.replace("\n", "\n   "))

        elif a.cmd == "mark-handled":
            from models import ContactMessage
            m = await db.get(ContactMessage, a.id)
            if not m:
                sys.exit("No such message")
            m.handled = True
            await db.commit()
            print(f"Marked message {a.id} handled")
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1:]))
