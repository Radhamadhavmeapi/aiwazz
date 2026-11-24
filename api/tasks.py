"""Scheduled tasks (registered with scheduler.every)."""
from scheduler import every


@every("plan-sweep", 3600, first_delay=20)
async def plan_sweep(sessionmaker, app) -> str:
    from usage import expire_plans, purge_old_invite_requests
    async with sessionmaker() as db:
        n = await expire_plans(db)
        m = await purge_old_invite_requests(db)
    return f"{n} plan(s) ended, {m} old invite request(s) deleted"


@every("dunning", 3600, first_delay=60)
async def dunning(sessionmaker, app) -> str:
    from billing import dunning as d
    async with sessionmaker() as db:
        return await d.run(db)


@every("abuse-signals", 3600, first_delay=120)
async def abuse_signals(sessionmaker, app) -> str:
    """Automatic flags: unusual volume (last hour ≫ the user's normal) and many new accounts from one IP."""
    from datetime import timedelta

    from sqlalchemy import func, select

    from db import utcnow
    from models import Flag, Generation, User
    now = utcnow()
    made = 0
    async with sessionmaker() as db:
        hour = dict((await db.execute(select(Generation.user_id, func.sum(Generation.text_chars)).where(
            Generation.created_at >= now - timedelta(hours=1)).group_by(Generation.user_id))).all())
        for uid, chars in hour.items():
            week = (await db.execute(select(func.coalesce(func.sum(Generation.text_chars), 0)).where(
                Generation.user_id == uid, Generation.created_at >= now - timedelta(days=7),
                Generation.created_at < now - timedelta(hours=1)))).scalar_one()
            normal = int(week) / (7 * 24)
            if int(chars) >= max(20000, 10 * normal):
                recent = (await db.execute(select(Flag.id).where(Flag.user_id == uid, Flag.source == "volume",
                                                                 Flag.created_at >= now - timedelta(hours=24)))).first()
                if not recent:
                    db.add(Flag(source="volume", user_id=uid, category="other", severity="medium", rule_name="Volume spike",
                                detail=f"{int(chars):,} characters in the last hour (normal ≈ {normal:,.0f}/hour)"))
                    made += 1
        rows = (await db.execute(select(User.consent_ip, func.count(), func.max(User.id)).where(
            User.created_at >= now - timedelta(days=7), User.consent_ip.is_not(None)).group_by(User.consent_ip))).all()
        for ip, n, newest in rows:
            if n >= 3:
                key = f"{n} accounts from {ip} in 7 days"
                seen = (await db.execute(select(Flag.id).where(Flag.source == "multi_account", Flag.detail.contains(f"from {ip} ")))).first()
                if not seen:
                    db.add(Flag(source="multi_account", user_id=newest, category="other", severity="medium",
                                rule_name="Many accounts from one IP", detail=key))
                    made += 1
        await db.commit()
    return f"{made} new flag(s)"


@every("alerts", 300, first_delay=90, log_ok=False)
async def alerts(sessionmaker, app) -> str:
    from admin import health
    async with sessionmaker() as db:
        return await health.check_and_notify(app, db)


@every("backup-check", 1800, first_delay=150, log_ok=False)
async def backup_daily(sessionmaker, app) -> str:
    """Once a day after 02:00 IST (skipped until a backup passphrase is set)."""
    from datetime import timedelta

    from admin import health
    from admin.jobs import run_logged
    from db import utcnow
    from settings import get_settings
    if not get_settings().backup_passphrase:
        return "no passphrase"
    now_ist = utcnow() + timedelta(hours=5, minutes=30)
    latest = health.list_backups()[:1]
    today = now_ist.strftime("%Y%m%d")
    if now_ist.hour < 2 or (latest and latest[0]["name"].startswith(f"aiwazz-{today}")):
        return "not due"
    await run_logged(sessionmaker, "backup", health.make_backup)
    return "ran"
