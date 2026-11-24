"""Invite requests, time-limited plans (set-plan --until) and the mailer staying off by default."""
from datetime import timedelta

from db import utcnow


def test_invite_request_saved_once_per_email(anon, app_env):
    body = {"email": "Friend@Example.com", "name": "Friend", "use_case": "Hindi reels"}
    assert anon.post("/api/auth/invite-request", json=body).status_code == 202
    assert anon.post("/api/auth/invite-request", json=body | {"use_case": "YouTube too"}).status_code == 202
    from tests.conftest import _run

    async def rows():
        from sqlalchemy import select
        from db import make_engine, make_sessionmaker
        from models import InviteRequest
        eng = make_engine(app_env)
        async with make_sessionmaker(eng)() as db:
            out = (await db.execute(select(InviteRequest))).scalars().all()
        await eng.dispose()
        return out
    r = _run(rows())
    assert len(r) == 1 and r[0].email == "friend@example.com" and r[0].use_case == "YouTube too" and r[0].status == "new"


def test_invite_request_needs_csrf_and_rate_limits(anon):
    tok = anon.headers.pop("X-CSRF-Token")
    assert anon.post("/api/auth/invite-request", json={"email": "a@example.com"}).status_code == 403
    anon.headers["X-CSRF-Token"] = tok
    codes = [anon.post("/api/auth/invite-request", json={"email": f"u{i}@example.com"}).status_code for i in range(6)]
    assert codes[:5] == [202] * 5 and codes[5] == 429


def test_invite_request_honeypot_and_validation(anon):
    assert anon.post("/api/auth/invite-request", json={"email": "bot@example.com", "website": "x"}).status_code == 202
    assert anon.post("/api/auth/invite-request", json={"email": "not-an-email"}).status_code == 422


def test_plan_until_active_then_free(client, set_plan):
    set_plan("creator", until=utcnow() + timedelta(days=90))
    me = client.get("/api/auth/me").json()
    assert me["plan"] == "creator" and me["api_access"] is True and me["plan_until"]
    u = client.get("/api/usage").json()
    assert u["allowance"] == 200000 and u["plan_until"]
    set_plan("creator", until=utcnow() - timedelta(minutes=1))     # ended, sweep not run yet
    me = client.get("/api/auth/me").json()
    assert me["plan"] == "free" and me["api_access"] is False and me["plan_until"] is None
    assert client.get("/api/usage").json()["allowance"] == 5000


def test_expire_plans_sweep(client, set_plan, app_env):
    set_plan("creator", until=utcnow() - timedelta(minutes=1))
    from tests.conftest import _run

    async def sweep():
        from sqlalchemy import select
        from db import make_engine, make_sessionmaker
        from models import User
        from usage import expire_plans
        eng = make_engine(app_env)
        async with make_sessionmaker(eng)() as db:
            n = await expire_plans(db)
            u = (await db.execute(select(User))).scalar_one()
        await eng.dispose()
        return n, u.plan, u.plan_until
    assert _run(sweep()) == (1, "free", None)


def test_mailer_is_off_by_default():
    import asyncio

    import mailer
    from settings import get_settings
    assert get_settings().mail_enabled is False
    assert asyncio.run(mailer.send(mailer.build("x@example.com", "s", "t"))) is False
