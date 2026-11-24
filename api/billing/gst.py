"""GST rules for AiWazz invoices: prices, tax split, GSTIN check, financial-year invoice numbers.

Prices in legal/legal.json exclude GST (pricesIncludeGst=false). We charge price + 18 % GST.
Supplier: RADHAMADHAV WEBSTORE LLP, Maharashtra (state code 27). Place of supply = the buyer's state:
same state → CGST 9 % + SGST 9 %; other state → IGST 18 %.
"""
import json
import re
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from settings import API_DIR

LEGAL = json.loads((API_DIR.parent / "legal" / "legal.json").read_text())
GST_RATE = int(LEGAL.get("gstRatePercent", 18))
SUPPLIER_STATE = LEGAL.get("gstin", "27")[:2]
PERIODS = ("monthly", "yearly")
PAID_PLANS = ("starter", "creator", "pro")
IST = timedelta(hours=5, minutes=30)

STATES = {
    "01": "Jammu and Kashmir", "02": "Himachal Pradesh", "03": "Punjab", "04": "Chandigarh", "05": "Uttarakhand",
    "06": "Haryana", "07": "Delhi", "08": "Rajasthan", "09": "Uttar Pradesh", "10": "Bihar", "11": "Sikkim",
    "12": "Arunachal Pradesh", "13": "Nagaland", "14": "Manipur", "15": "Mizoram", "16": "Tripura", "17": "Meghalaya",
    "18": "Assam", "19": "West Bengal", "20": "Jharkhand", "21": "Odisha", "22": "Chhattisgarh", "23": "Madhya Pradesh",
    "24": "Gujarat", "26": "Dadra and Nagar Haveli and Daman and Diu", "27": "Maharashtra", "29": "Karnataka",
    "30": "Goa", "31": "Lakshadweep", "32": "Kerala", "33": "Tamil Nadu", "34": "Puducherry",
    "35": "Andaman and Nicobar Islands", "36": "Telangana", "37": "Andhra Pradesh", "38": "Ladakh",
}

_GSTIN = re.compile(r"^\d{2}[A-Z]{5}\d{4}[A-Z][1-9A-Z]Z[0-9A-Z]$")
_CHARS = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"


def gstin_problem(gstin: str, state: str) -> str | None:
    """None if valid (format + check digit + matches the chosen state), else a user-facing message."""
    if not _GSTIN.match(gstin):
        return "That GSTIN doesn't look right (15 characters, like 27ABCDE1234F1Z5)"
    total = 0
    for i, ch in enumerate(gstin[:14]):
        v = _CHARS.index(ch) * (2 if i % 2 else 1)
        total += v // 36 + v % 36
    if _CHARS[(36 - total % 36) % 36] != gstin[14]:
        return "That GSTIN has a typo (the check digit doesn't match)"
    if gstin[:2] != state:
        return f"This GSTIN is registered in {STATES.get(gstin[:2], 'another state')}; pick that state"
    return None


def plan_prices() -> dict[str, dict]:
    """{plan: {name, monthly, yearly, yearly_per_month, characters}} in whole rupees, excl. GST.
    Yearly = exactly 12 × the discounted monthly price (same rule as the pricing page)."""
    disc = LEGAL.get("yearlyDiscountPercent", 0)
    out = {}
    for p in LEGAL["plans"]:
        if p["id"] not in PAID_PLANS:
            continue
        per_month = round(p["priceMonthly"] * (1 - disc / 100))
        out[p["id"]] = {"name": p["name"], "monthly": p["priceMonthly"], "yearly": per_month * 12,
                        "yearly_per_month": per_month, "characters": p["characters"]}
    return out


def charge_paise(plan: str, period: str) -> tuple[int, int]:
    """(taxable_paise, total_paise incl. GST) for one billing period."""
    base = plan_prices()[plan][period] * 100
    return base, base * (100 + GST_RATE) // 100


@dataclass
class TaxSplit:
    taxable: int
    cgst: int
    sgst: int
    igst: int
    total: int


def split_tax(total_paise: int, buyer_state: str) -> TaxSplit:
    """Work back from the amount actually paid, so the invoice always adds up to it exactly."""
    taxable = round(total_paise * 100 / (100 + GST_RATE))
    tax = total_paise - taxable
    if buyer_state == SUPPLIER_STATE:
        cgst = tax // 2
        return TaxSplit(taxable, cgst, tax - cgst, 0, total_paise)
    return TaxSplit(taxable, 0, 0, tax, total_paise)


def financial_year(when_utc: datetime) -> str:
    """Indian FY (April–March) of a naive-UTC time, e.g. 2026-27."""
    ist = when_utc + IST
    start = ist.year if ist.month >= 4 else ist.year - 1
    return f"{start}-{str(start + 1)[2:]}"


async def next_invoice_number(db: AsyncSession, when_utc: datetime) -> str:
    """AWZ/2026-27/00001: consecutive per financial year (GST rule 46), row-locked against races."""
    from models import InvoiceCounter
    fy = financial_year(when_utc)
    row = (await db.execute(select(InvoiceCounter).where(InvoiceCounter.fy == fy).with_for_update())).scalar_one_or_none()
    if row is None:
        row = InvoiceCounter(fy=fy, last=0)
        db.add(row)
    row.last += 1
    await db.flush()
    return f"AWZ/{fy}/{row.last:05d}"


def rupees(paise: int) -> str:
    """12345 → '₹123.45' with Indian digit grouping."""
    r, p = divmod(paise, 100)
    s = str(r)
    if len(s) > 3:
        head, tail = s[:-3], s[-3:]
        head = re.sub(r"(\d)(?=(\d\d)+$)", r"\1,", head)
        s = f"{head},{tail}"
    return f"₹{s}.{p:02d}"
