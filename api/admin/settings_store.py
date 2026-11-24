"""Runtime settings stored in app_settings (JSON), with defaults here. Small in-process cache (single API worker)."""
import json
import time
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models import AppSetting

DEFAULTS: dict[str, Any] = {
    "security.admin_ip_allowlist": {"enabled": False, "cidrs": []},
    # signup_mode: invite (invite code required) | open (code optional) | closed (no new accounts)
    "general": {"product_name": "AiWazz", "support_email": "support@aiwazz.in", "signup_mode": "invite"},
    # Dunning: days of paid access after a failed renewal (emails on day 0, 3, 7), then Free.
    "billing": {"grace_days": 7, "dunning_emails": True},
    "referrals": {"enabled": False, "reward_chars_referrer": 10000, "reward_chars_referred": 5000,
                  "require_paid": True},
}
_cache: dict[str, tuple[float, Any]] = {}
TTL = 10.0


async def get(db: AsyncSession, key: str) -> Any:
    hit = _cache.get(key)
    if hit and time.monotonic() - hit[0] < TTL:
        return hit[1]
    row = await db.get(AppSetting, key)
    default = DEFAULTS.get(key)
    value = json.loads(row.value_json) if row else default
    if isinstance(default, dict) and isinstance(value, dict):
        value = {**default, **value}
    _cache[key] = (time.monotonic(), value)
    return value


async def put(db: AsyncSession, key: str, value: Any, by: int | None) -> None:
    row = await db.get(AppSetting, key)
    if row is None:
        db.add(AppSetting(key=key, value_json=json.dumps(value), updated_by=by))
    else:
        row.value_json, row.updated_by = json.dumps(value), by
    _cache.pop(key, None)


def clear_cache() -> None:
    _cache.clear()


async def all_values(db: AsyncSession) -> dict[str, Any]:
    rows = {r.key: json.loads(r.value_json) for r in (await db.execute(select(AppSetting))).scalars()}
    out = {}
    for k, d in DEFAULTS.items():
        v = rows.get(k, d)
        out[k] = {**d, **v} if isinstance(d, dict) and isinstance(v, dict) else v
    return out
