"""Account deletion, shared by self-service delete (auth/routes.py), the admin panel and manage.py delete-user.

Deletes sessions, API keys, history + audio, pronunciations, 2FA; keeps invoices/payments/subscriptions detached
(8-year tax records, Privacy Policy §3) and writes a deletion_log reference. Cancelling a live Razorpay subscription
is the caller's job (it needs the network and must fail closed)."""
import secrets

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from auth.security import sha256
from db import utcnow
from models import ApiKey, DeletionLog, Generation, Invite, Invoice, Payment, Subscription, User, UserSession
from settings import get_settings


async def delete_user_data(db: AsyncSession, user: User) -> tuple[str, int]:
    """Returns (deletion reference, generations deleted). Caller commits."""
    from models import BackupCode, Pronunciation, TotpSecret
    for model in (Invoice, Payment, Subscription):
        await db.execute(update(model).where(model.user_id == user.id).values(user_id=None))
    gen_ids = (await db.execute(select(Generation.id).where(Generation.user_id == user.id))).scalars().all()
    audio_dir = get_settings().audio_dir
    for gid in gen_ids:
        for ext in ("mp3", "wav", "json"):
            (audio_dir / f"{gid}.{ext}").unlink(missing_ok=True)
    # Explicit deletes (portable; doesn't rely on FK cascades)
    await db.execute(delete(Generation).where(Generation.user_id == user.id))
    await db.execute(delete(ApiKey).where(ApiKey.user_id == user.id))
    await db.execute(delete(UserSession).where(UserSession.user_id == user.id))
    await db.execute(delete(Pronunciation).where(Pronunciation.user_id == user.id))
    await db.execute(delete(BackupCode).where(BackupCode.user_id == user.id))
    await db.execute(delete(TotpSecret).where(TotpSecret.user_id == user.id))
    await db.execute(update(Invite).where(Invite.created_by == user.id).values(created_by=None))
    for extra in _extra_cleanups:
        await extra(db, user)
    reference = f"DEL-{utcnow():%Y%m%d}-{secrets.token_hex(3).upper()}"
    db.add(DeletionLog(reference=reference, email_hash=sha256(user.email), generations_deleted=len(gen_ids)))
    await db.delete(user)
    return reference, len(gen_ids)


# Later phases register cleanups for their own per-user tables (notes, tags, ...).
_extra_cleanups: list = []


def on_delete(fn):
    _extra_cleanups.append(fn)
    return fn
