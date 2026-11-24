"""Voice + style catalogue as users see it: tts/voices.py and tts/styles.py plus admin overrides (admin → Voices &
styles): enabled, display name, description, tags, order, "new" badge and a minimum plan per voice."""
import time

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models import StyleSetting, User, VoiceSetting

from .styles import STYLES
from .voices import VOICES

PLAN_RANK = {"free": 0, "starter": 1, "creator": 2, "pro": 3}
# Card descriptions (were only in the dashboard before; editable now).
DEFAULT_TONES = {
    "hf_alpha": "Warm, clear", "hf_beta": "Bright, friendly", "hm_omega": "Deep, calm", "hm_psi": "Steady, narrator",
    "af_heart": "Warm, natural", "af_bella": "Expressive", "af_nicole": "Soft, close", "am_michael": "Confident",
    "am_fenrir": "Bold", "am_puck": "Playful", "bf_emma": "Polished", "bf_isabella": "Elegant",
    "bm_george": "Classic narrator", "bm_fable": "Storyteller",
}
ACCENT = {"h": "Hindi", "a": "US English", "b": "UK English"}
_cache: dict[str, tuple[float, dict]] = {}
TTL = 30.0


def clear_cache() -> None:
    _cache.clear()


async def voice_settings(db: AsyncSession) -> dict[str, VoiceSetting]:
    hit = _cache.get("v")
    if hit and time.monotonic() - hit[0] < TTL:
        return hit[1]
    rows = {r.voice_id: r for r in (await db.execute(select(VoiceSetting))).scalars()}
    for r in rows.values():
        db.expunge(r)
    _cache["v"] = (time.monotonic(), rows)
    return rows


async def style_settings(db: AsyncSession) -> dict[str, StyleSetting]:
    hit = _cache.get("s")
    if hit and time.monotonic() - hit[0] < TTL:
        return hit[1]
    rows = {r.style_id: r for r in (await db.execute(select(StyleSetting))).scalars()}
    for r in rows.values():
        db.expunge(r)
    _cache["s"] = (time.monotonic(), rows)
    return rows


def voice_meta(vid: str, base: dict, st: VoiceSetting | None, index: int) -> dict:
    default_tags = [base.get("gender", ""), ACCENT.get(base.get("lang", ""), "")]
    return {
        "enabled": st.enabled if st else True,
        "display_name": (st.display_name if st and st.display_name else base.get("name", vid)),
        "tone": (st.description if st and st.description else DEFAULT_TONES.get(vid, "")),
        "tags": [t for t in (st.tags.split(",") if st and st.tags else default_tags) if t],
        "sort_order": st.sort_order if st else index,
        "is_new": bool(st and st.is_new),
        "min_plan": st.min_plan if st else "free",
    }


def plan_allows(user: User | None, min_plan: str) -> bool:
    if user is not None and user.is_admin:
        return True
    plan = user.effective_plan if user else "free"
    return PLAN_RANK.get(plan, 0) >= PLAN_RANK.get(min_plan, 0)


async def builtin_voices(db: AsyncSession, user: User | None, include_disabled: bool = False) -> list[dict]:
    st = await voice_settings(db)
    out = []
    for i, v in enumerate(VOICES.values()):
        meta = voice_meta(v.id, v.to_dict(), st.get(v.id), i)
        if not meta["enabled"] and not include_disabled:
            continue
        d = v.to_dict() | meta
        d["name"] = meta["display_name"]
        d["available"] = plan_allows(user, meta["min_plan"])
        out.append(d)
    return sorted(out, key=lambda d: d["sort_order"])


async def check_voice(db: AsyncSession, user: User, voice_id: str) -> None:
    """Raise if the voice is switched off or needs a higher plan (built-in and clone voices alike)."""
    st = (await voice_settings(db)).get(voice_id)
    if st is None:
        return
    if not st.enabled and not user.is_admin:
        raise HTTPException(422, "This voice isn't available right now. Please pick another voice.")
    if not plan_allows(user, st.min_plan):
        raise HTTPException(403, f"This voice is included in the {st.min_plan.title()} plan and above.")


async def styles(db: AsyncSession, include_disabled: bool = False) -> list[dict]:
    st = await style_settings(db)
    out = []
    for i, s in enumerate(STYLES.values()):
        o = st.get(s.id)
        if o and not o.enabled and not include_disabled:
            continue
        d = s.to_dict() | {"enabled": o.enabled if o else True, "sort_order": o.sort_order if o else i}
        if o and o.display_name:
            d["name"] = o.display_name
        if o and o.description:
            d["description"] = o.description
        out.append(d)
    return sorted(out, key=lambda d: d["sort_order"])


async def check_style(db: AsyncSession, user: User, style_id: str | None) -> None:
    if not style_id:
        return
    o = (await style_settings(db)).get(style_id)
    if o is not None and not o.enabled and not user.is_admin:
        raise HTTPException(422, "This style isn't available right now")
