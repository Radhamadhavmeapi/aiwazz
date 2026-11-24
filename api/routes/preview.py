"""Owner-only preview pages for voice work.

GET /api/preview/custom-voice/          phase 13 custom voice samples (data/voices/hi_reel_narrator_m1/lab/)
GET /api/preview/voice-lab/             phase 10 Voice Lab samples (data/preview/voice-lab/, tools/voice_lab_page.py)
GET /api/preview/<name>/{file}          an MP3 / JSON / font next to the page
Files live outside the web root (gitignored). Shown inside the admin panel (Voices & styles): needs an unlocked admin
session (2FA) with voices.read; everyone else (including API keys and locked sessions) gets the same 404. Never indexed.
"""
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse, RedirectResponse

from auth.deps import Principal, optional_principal
from db import get_db

router = APIRouter(prefix="/api/preview", include_in_schema=False)
DATA = Path(__file__).resolve().parents[2] / "data"
ROOTS = {"custom-voice": DATA / "voices" / "hi_reel_narrator_m1" / "lab", "voice-lab": DATA / "preview" / "voice-lab"}
TYPES = {".html": "text/html; charset=utf-8", ".mp3": "audio/mpeg", ".json": "application/json", ".woff2": "font/woff2"}
NOINDEX = {"X-Robots-Tag": "noindex, nofollow, noarchive", "Cache-Control": "private, no-store"}


async def _allowed(name: str, p: Principal | None, db) -> Path:
    from admin import rbac
    from admin.deps import unlocked_state
    from models import TotpSecret
    root = ROOTS.get(name)
    if root is None or p is None or p.via != "session" or not p.user.is_staff or p.read_only:
        raise HTTPException(404, "Not found")
    t = await db.get(TotpSecret, p.user.id)
    if t is None or t.enabled_at is None or not unlocked_state(p) or not rbac.has(p.user.role, "voices.read"):
        raise HTTPException(404, "Not found")
    return root


@router.get("/{name}")
async def preview_root(name: str, p: Principal | None = Depends(optional_principal), db=Depends(get_db)):
    await _allowed(name, p, db)
    return RedirectResponse(f"/api/preview/{name}/", status_code=308, headers=NOINDEX)


@router.get("/{name}/{path:path}")
async def preview_file(name: str, path: str = "", p: Principal | None = Depends(optional_principal), db=Depends(get_db)):
    root = await _allowed(name, p, db)
    target = (root / (path or "index.html")).resolve()
    if not target.is_relative_to(root.resolve()) or target.suffix not in TYPES or not target.is_file():
        raise HTTPException(404, "Not found")
    headers = dict(NOINDEX)
    if target.suffix in (".mp3", ".woff2"):
        headers["Cache-Control"] = "private, max-age=3600"
    return FileResponse(target, media_type=TYPES[target.suffix], headers=headers)
