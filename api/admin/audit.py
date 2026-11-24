"""Append-only admin audit log. Call audit() inside the same transaction as the change, so both commit together."""
import json
from typing import Any

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from auth.deps import client_ip
from models import AdminAudit, User

_SECRET_HINTS = ("password", "secret", "token", "hash", "otp", "backup", "key_enc")


def _clean(v: Any) -> Any:
    if isinstance(v, dict):
        return {k: ("[redacted]" if any(h in k.lower() for h in _SECRET_HINTS) else _clean(x)) for k, x in v.items()}
    if isinstance(v, (list, tuple)):
        return [_clean(x) for x in v]
    return v


def diff(before: dict | None, after: dict | None) -> tuple[dict | None, dict | None]:
    """Keep only the keys that changed (both sides), so the log shows exactly what moved."""
    if before is None or after is None:
        return before, after
    keys = [k for k in sorted(set(before) | set(after)) if before.get(k) != after.get(k)]
    return {k: before.get(k) for k in keys}, {k: after.get(k) for k in keys}


def _dump(v: Any) -> str | None:
    return None if v is None else json.dumps(_clean(v), default=str, ensure_ascii=False, sort_keys=True)[:60000]


def audit(db: AsyncSession, request: Request | None, actor: User | None, action: str, *, target_type: str = "",
          target_id: Any = "", label: str = "", before: dict | None = None, after: dict | None = None,
          reason: str = "", full: bool = False) -> AdminAudit:
    b, a = (before, after) if full else diff(before, after)
    row = AdminAudit(
        actor_id=actor.id if actor else None, actor_email=(actor.email if actor else "system")[:254],
        actor_role=(actor.role if actor else "system")[:16], action=action[:64], target_type=target_type[:32],
        target_id=str(target_id)[:64], target_label=(label or "")[:254], before_json=_dump(b), after_json=_dump(a),
        reason=(reason or "")[:500],
        ip=(client_ip(request) if request else "")[:45],
        user_agent=((request.headers.get("user-agent") or "") if request else "")[:255],
    )
    db.add(row)
    return row
