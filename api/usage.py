"""Plans and monthly character allowance (legal/legal.json is the single source of truth for plans).

- Characters are counted from SUCCESSFUL generations only (failed jobs are never charged).
- Queued/running jobs are reserved, so nobody can queue past their allowance.
- The period is the calendar month in India time (IST); billing periods replace this when payments launch.
- Admins are unlimited and always have API access.
"""
import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from models import Generation, User
from settings import API_DIR

IST = timedelta(hours=5, minutes=30)
API_PLANS = {"creator", "pro"}


def _plans() -> dict[str, dict]:
    path = API_DIR.parent / "legal" / "legal.json"
    data = json.loads(path.read_text()) if path.exists() else {"plans": []}
    return {p["id"]: p for p in data.get("plans", [])} or {"free": {"id": "free", "name": "Free", "characters": 5000}}


PLANS = _plans()


def period_bounds(now_utc: datetime | None = None) -> tuple[datetime, datetime]:
    """Current calendar month in IST, returned as naive UTC [start, end)."""
    now = (now_utc or datetime.now(UTC).replace(tzinfo=None)) + IST
    start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    end = (start + timedelta(days=32)).replace(day=1)
    return start - IST, end - IST


@dataclass
class Usage:
    plan: str
    plan_name: str
    plan_until: datetime | None
    unlimited: bool
    allowance: int | None
    used: int        # successful generations this period
    reserved: int    # queued / running
    period_start: datetime
    period_end: datetime

    @property
    def remaining(self) -> int | None:
        return None if self.allowance is None else max(0, self.allowance - self.used - self.reserved)

    def to_dict(self) -> dict:
        iso = lambda d: d.isoformat() + "Z"  # noqa: E731
        return {"plan": self.plan, "plan_name": self.plan_name,
                "plan_until": iso(self.plan_until) if self.plan_until else None, "unlimited": self.unlimited, "allowance": self.allowance,
                "used": self.used, "reserved": self.reserved, "remaining": self.remaining,
                "period_start": iso(self.period_start), "period_end": iso(self.period_end),
                "api_access": self.unlimited or self.plan in API_PLANS}


async def get_usage(db: AsyncSession, user: User) -> Usage:
    start, end = period_bounds()
    current = user.effective_plan
    plan = PLANS.get(current) or PLANS.get("free")
    unlimited = user.is_admin
    rows = (await db.execute(
        select(Generation.status, func.coalesce(func.sum(Generation.text_chars), 0))
        .where(Generation.user_id == user.id, Generation.created_at >= start, Generation.created_at < end,
               Generation.status.in_(("done", "queued", "running")))
        .group_by(Generation.status))).all()
    by = {s: int(n) for s, n in rows}
    return Usage(plan=current, plan_name=plan["name"], plan_until=user.plan_until if current != "free" else None,
                 unlimited=unlimited,
                 allowance=None if unlimited else int(plan["characters"]), used=by.get("done", 0),
                 reserved=by.get("queued", 0) + by.get("running", 0), period_start=start, period_end=end)


def has_api_access(user: User) -> bool:
    return user.is_admin or user.effective_plan in API_PLANS


async def expire_plans(db: AsyncSession) -> int:
    """Move every user whose time-limited plan has ended back to Free. Returns how many were changed."""
    from sqlalchemy import update

    from db import utcnow
    res = await db.execute(update(User).where(User.plan_until.is_not(None), User.plan_until <= utcnow())
                           .values(plan="free", plan_until=None))
    await db.commit()
    return res.rowcount or 0


async def purge_old_invite_requests(db: AsyncSession, days: int = 365) -> int:
    """Privacy Policy §3: invite requests are deleted 12 months after the last request."""
    from sqlalchemy import delete

    from db import utcnow
    from models import InviteRequest
    res = await db.execute(delete(InviteRequest).where(InviteRequest.updated_at < utcnow() - timedelta(days=days)))
    await db.commit()
    return res.rowcount or 0
