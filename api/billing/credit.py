"""GST credit notes (refunds and voided invoices). Series AWZ-CN/<FY>/<n>, consecutive per FY, row-locked."""
import asyncio

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from db import utcnow
from models import CreditNote, CreditNoteCounter, Invoice, Refund
from settings import get_settings

from .gst import financial_year, split_tax


async def next_credit_note_number(db: AsyncSession, when_utc) -> str:
    fy = financial_year(when_utc)
    row = (await db.execute(select(CreditNoteCounter).where(CreditNoteCounter.fy == fy).with_for_update())).scalar_one_or_none()
    if row is None:
        row = CreditNoteCounter(fy=fy, last=0)
        db.add(row)
    row.last += 1
    await db.flush()
    return f"AWZ-CN/{fy}/{row.last:05d}"


async def credited_paise(db: AsyncSession, invoice_id: int) -> int:
    return int((await db.execute(select(func.coalesce(func.sum(CreditNote.total_paise), 0))
                                 .where(CreditNote.invoice_id == invoice_id))).scalar_one())


async def issue_credit_note(db: AsyncSession, inv: Invoice, amount_paise: int, kind: str, reason: str,
                            refund: Refund | None = None) -> CreditNote:
    """Tax split worked back from the credited amount, same place of supply as the invoice."""
    left = inv.total_paise - await credited_paise(db, inv.id)
    if amount_paise <= 0 or amount_paise > left:
        raise ValueError(f"Credit must be between ₹0.01 and the uncredited ₹{left / 100:,.2f}")
    t = split_tax(amount_paise, inv.buyer_state)
    now = utcnow()
    cn = CreditNote(number=await next_credit_note_number(db, now), invoice_id=inv.id, refund_id=refund.id if refund else None,
                    user_id=inv.user_id, kind=kind, reason=reason[:255], issued_at=now, taxable_paise=t.taxable,
                    cgst_paise=t.cgst, sgst_paise=t.sgst, igst_paise=t.igst, total_paise=t.total)
    db.add(cn)
    await db.flush()
    if refund is not None:
        refund.credit_note_id = cn.id
    return cn


def credit_note_path(cn: CreditNote):
    return get_settings().invoice_dir / f"{cn.number.replace('/', '-')}.pdf"


async def ensure_credit_note_pdf(db: AsyncSession, cn: CreditNote, force: bool = False):
    from . import invoice_pdf
    p = credit_note_path(cn)
    if force or not p.exists():
        inv = await db.get(Invoice, cn.invoice_id)
        await asyncio.to_thread(invoice_pdf.render, inv, p, cn)
    return p
