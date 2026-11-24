"""Moderation: rules checked on every script at submit time, blocklist checks, automatic flags.

Keyword rules match whole words/phrases case-insensitively (Devanagari too); regex rules use Python `re` with a
length cap. Only the matched term is stored in a flag, never the script (that stays under the privacy rule)."""
import ipaddress
import re
import time
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models import BlockEntry, Flag, ModerationRule, User

_cache: tuple[float, list] = (0.0, [])
TTL = 30.0


@dataclass
class Match:
    rule: ModerationRule
    term: str


def compile_rule(r: ModerationRule) -> re.Pattern | None:
    try:
        if r.kind == "regex":
            return re.compile(r.pattern[:2000], re.IGNORECASE)
        terms = [t.strip() for t in r.pattern.split(",") if t.strip()]
        if not terms:
            return None
        alt = "|".join(re.escape(t).replace(r"\ ", r"\s+") for t in sorted(terms, key=len, reverse=True))
        return re.compile(rf"(?<![\w]){'(?:' + alt + ')'}(?![\w])", re.IGNORECASE)
    except re.error:
        return None


def clear_cache() -> None:
    global _cache
    _cache = (0.0, [])


async def _rules(db: AsyncSession) -> list[tuple[ModerationRule, re.Pattern]]:
    global _cache
    if time.monotonic() - _cache[0] < TTL:
        return _cache[1]
    rows = (await db.execute(select(ModerationRule).where(ModerationRule.active.is_(True)))).scalars().all()
    compiled = [(r, p) for r in rows if (p := compile_rule(r)) is not None]
    for r, _ in compiled:
        db.expunge(r)
    _cache = (time.monotonic(), compiled)
    return compiled


async def screen(db: AsyncSession, text: str) -> list[Match]:
    out = []
    for rule, pat in await _rules(db):
        m = pat.search(text[:20000])
        if m:
            out.append(Match(rule, m.group(0)[:100]))
    return out


async def record(db: AsyncSession, user: User, matches: list[Match], generation_id: str | None, blocked: bool) -> None:
    for m in matches:
        db.add(Flag(source="rule", user_id=user.id, generation_id=generation_id, rule_id=m.rule.id, rule_name=m.rule.name,
                    category=m.rule.category, severity=m.rule.severity, matched=m.term, blocked=blocked,
                    detail="Job refused" if blocked else ""))


async def is_blocked(db: AsyncSession, email: str = "", ip: str = "") -> bool:
    email = email.lower().strip()
    domain = email.split("@")[-1] if "@" in email else ""
    rows = (await db.execute(select(BlockEntry))).scalars().all()
    for b in rows:
        if b.kind == "email" and email and b.value == email:
            return True
        if b.kind == "domain" and domain and (domain == b.value or domain.endswith("." + b.value)):
            return True
        if b.kind == "ip" and ip:
            try:
                if ipaddress.ip_address(ip) in ipaddress.ip_network(b.value, strict=False):
                    return True
            except ValueError:
                continue
    return False
