"""Owner-only preview pages for voice work (phase 13: custom voice samples).

GET /api/preview/custom-voice/          the sample page (HTML)
GET /api/preview/custom-voice/{file}    an MP3 or JSON next to it
Files live outside the web root in data/voices/hi_reel_narrator_m1/lab/ (gitignored). Admin session only; everyone
else (including API keys) gets the same 404 as a missing page. Never indexed.
"""
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse

from auth.deps import Principal, optional_principal

router = APIRouter(prefix="/api/preview", include_in_schema=False)
ROOTS = {"custom-voice": Path(__file__).resolve().parents[2] / "data" / "voices" / "hi_reel_narrator_m1" / "lab"}
TYPES = {".html": "text/html; charset=utf-8", ".mp3": "audio/mpeg", ".json": "application/json"}
NOINDEX = {"X-Robots-Tag": "noindex, nofollow, noarchive", "Cache-Control": "private, no-store"}


@router.get("/{name}/{path:path}")
async def preview_file(name: str, path: str = "", p: Principal | None = Depends(optional_principal)):
    root = ROOTS.get(name)
    if root is None or p is None or p.via != "session" or not p.user.is_admin:
        raise HTTPException(404, "Not found")
    target = (root / (path or "index.html")).resolve()
    if not target.is_relative_to(root.resolve()) or target.suffix not in TYPES or not target.is_file():
        raise HTTPException(404, "Not found")
    headers = dict(NOINDEX)
    if target.suffix == ".mp3":
        headers["Cache-Control"] = "private, max-age=3600"
    return FileResponse(target, media_type=TYPES[target.suffix], headers=headers)
