"""A5 (started in A1): global pronunciation dictionary, edited only here (2FA + pronunciations.write, audited)."""
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from auth.deps import Principal, csrf_protect
from db import get_db
from models import Pronunciation
from routes.pronunciations import EntryIn, _list, _out, _upsert

from ..audit import audit
from ..deps import require_perm, staff_principal

router = APIRouter(prefix="/api/admin", dependencies=[Depends(staff_principal), Depends(csrf_protect)],
                   include_in_schema=False)


@router.get("/pronunciations")
async def list_global(p: Principal = Depends(require_perm("voices.read")), db: AsyncSession = Depends(get_db)):
    return {"items": [_out(r) for r in await _list(db, None)]}


@router.post("/pronunciations")
async def save_global(body: EntryIn, request: Request, p: Principal = Depends(require_perm("pronunciations.write")),
                      db: AsyncSession = Depends(get_db)):
    existing = {r.word_key: r for r in await _list(db, None)}.get(body.word.lower())
    before = {"word": existing.word, "say_as": existing.say_as} if existing else None
    row = await _upsert(db, None, body)
    audit(db, request, p.user, "pronunciation.global.save", target_type="pronunciation", target_id=row.id,
          label=row.word, before=before, after={"word": row.word, "say_as": row.say_as}, full=before is None)
    await db.commit()
    return _out(row)


@router.delete("/pronunciations/{entry_id}")
async def delete_global(entry_id: int, request: Request, p: Principal = Depends(require_perm("pronunciations.write")),
                        db: AsyncSession = Depends(get_db)):
    row = await db.get(Pronunciation, entry_id)
    if row is None or row.user_id is not None:
        raise HTTPException(404, "Not found")
    audit(db, request, p.user, "pronunciation.global.delete", target_type="pronunciation", target_id=row.id,
          label=row.word, before={"word": row.word, "say_as": row.say_as}, full=True)
    await db.delete(row)
    await db.commit()
    return {"ok": True}
