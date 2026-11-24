"""In-app announcements (banners) and the public changelog export (landing build)."""
import json
from datetime import timedelta

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from db import utcnow
from models import Announcement, ChangelogEntry, User


def audience_match(aud: str, user: User | None) -> bool:
    if aud == "all":
        return True
    if user is None:
        return False
    plan = user.effective_plan
    if aud == "admins":
        return user.is_staff
    if aud == "free":
        return plan == "free"
    if aud == "paid":
        return plan != "free"
    if aud.startswith("plan:"):
        return plan == aud[5:]
    return False


async def active_banners(db: AsyncSession, user: User | None) -> list[dict]:
    now = utcnow()
    rows = (await db.execute(select(Announcement).where(
        Announcement.active.is_(True), or_(Announcement.starts_at.is_(None), Announcement.starts_at <= now),
        or_(Announcement.ends_at.is_(None), Announcement.ends_at > now)).order_by(Announcement.id.desc()))).scalars().all()
    return [{"id": f"ann-{a.id}", "level": a.level, "text": a.text, "dismissible": a.dismissible}
            for a in rows if audience_match(a.audience, user)][:3]


async def export_changelog(db: AsyncSession) -> list[dict]:
    rows = (await db.execute(select(ChangelogEntry).where(ChangelogEntry.is_published.is_(True))
                             .order_by(ChangelogEntry.published_on.desc(), ChangelogEntry.id.desc()))).scalars().all()
    return [{"id": e.id, "title": e.title, "body": e.body_md, "tag": e.tag,
             "date": (e.published_on + timedelta(hours=5, minutes=30)).date().isoformat()} for e in rows]


def main() -> None:
    """python -m admin.announcements > landing/src/data/changelog.generated.json (run by tools/deploy-landing.sh)."""
    import asyncio

    from db import make_engine, make_sessionmaker
    from settings import get_settings

    async def go():
        eng = make_engine(get_settings().database_url)
        async with make_sessionmaker(eng)() as db:
            out = await export_changelog(db)
        await eng.dispose()
        return out
    print(json.dumps(asyncio.run(go()), ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
