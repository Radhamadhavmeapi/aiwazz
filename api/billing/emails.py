"""Billing emails (sent only when mail is enabled; see mailer.py)."""
from sqlalchemy.ext.asyncio import AsyncSession

import mailer
from models import Invoice

from .gst import rupees


async def send_invoice_email(db: AsyncSession, inv: Invoice) -> None:
    from .service import invoice_path
    msg = mailer.build(inv.buyer_email, f"Your AiWazz invoice {inv.number}",
                       f"Thanks for your payment of {rupees(inv.total_paise)} for the AiWazz {inv.plan.title()} plan ({inv.period}).\n\n"
                       f"Your GST invoice {inv.number} is attached. You can also download it any time from\n"
                       "https://login.aiwazz.in/settings (Billing → Invoices).\n\n— AiWazz\n")
    p = invoice_path(inv)
    if p.exists():
        msg.add_attachment(p.read_bytes(), maintype="application", subtype="pdf", filename=p.name)
    mailer.send_later(msg)
