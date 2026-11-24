"""GST tax invoice as PDF (fpdf2, DejaVu Sans for the ₹ sign). Company data comes only from legal/legal.json.

Contents follow CGST Rule 46: supplier name/address/GSTIN, consecutive invoice number, date, buyer name/address
(+ GSTIN if registered), place of supply (state + code), SAC, description, taxable value, tax rate and amounts,
total, and a computer-generated note.
"""
from datetime import timedelta
from pathlib import Path

from fpdf import FPDF

from .gst import GST_RATE, LEGAL, STATES, rupees

FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
FONT_BOLD = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
IST = timedelta(hours=5, minutes=30)
NAVY = (7, 13, 37)
MUTED = (71, 85, 105)
INDIGO = (45, 54, 219)


def _d(dt) -> str:
    return (dt + IST).strftime("%d %b %Y") if dt else "-"


def render(inv, path: Path, cn=None) -> Path:
    """inv: models.Invoice. cn: models.CreditNote → a credit note against inv instead. Writes the PDF, returns it."""
    doc = cn if cn is not None else inv
    plan_name = next((p["name"] for p in LEGAL["plans"] if p["id"] == inv.plan), inv.plan.title())
    sac = LEGAL.get("sacCode", "998439")
    pdf = FPDF(format="A4", unit="mm")
    pdf.set_auto_page_break(True, 18)
    pdf.add_font("dv", "", FONT)
    pdf.add_font("dv", "B", FONT_BOLD)
    pdf.set_title(f"Credit note {cn.number}" if cn else f"Tax invoice {inv.number}")
    pdf.set_author(LEGAL["legalName"])
    pdf.add_page()
    pdf.set_margins(18, 18, 18)
    W = pdf.w - 36

    # Header
    pdf.set_xy(18, 18)
    pdf.set_font("dv", "B", 20)
    pdf.set_text_color(*INDIGO)
    pdf.cell(W / 2, 10, "AiWazz")
    pdf.set_font("dv", "B", 14)
    pdf.set_text_color(*NAVY)
    pdf.cell(W / 2, 10, "CREDIT NOTE" if cn else "TAX INVOICE", align="R", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("dv", "", 9)
    pdf.set_text_color(*MUTED)
    pdf.cell(W / 2, 5, LEGAL.get("brand", "AiWazz"))
    pdf.cell(W / 2, 5, "Original for recipient", align="R", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(6)

    # Supplier | Invoice meta
    y = pdf.get_y()
    pdf.set_font("dv", "B", 9)
    pdf.set_text_color(*NAVY)
    pdf.cell(W * 0.55, 5, "From", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("dv", "", 9)
    supplier = [LEGAL["legalName"], LEGAL["address"], f"GSTIN: {LEGAL['gstin']}",
                f"State: {STATES.get(LEGAL['gstin'][:2], '')} ({LEGAL['gstin'][:2]})"]
    if LEGAL.get("llpin"):
        supplier.append(f"LLPIN: {LEGAL['llpin']}")
    supplier.append(f"{LEGAL.get('supportEmail', '')} · {LEGAL.get('phone', '')}")
    pdf.multi_cell(W * 0.55, 4.6, "\n".join(supplier), align="L", new_x="LMARGIN", new_y="NEXT")
    end_left = pdf.get_y()
    meta = [("Invoice number", inv.number), ("Invoice date", _d(inv.issued_at)),
            ("Place of supply", f"{STATES.get(inv.buyer_state, '')} ({inv.buyer_state})"),
            ("Reverse charge", "No")]
    if cn:
        meta = [("Credit note no.", cn.number), ("Date", _d(cn.issued_at))] + meta
    pdf.set_xy(18 + W * 0.58, y)
    for k, v in meta:
        pdf.set_x(18 + W * 0.58)
        pdf.set_font("dv", "", 9)
        pdf.set_text_color(*MUTED)
        pdf.cell(W * 0.18, 5, k)
        pdf.set_font("dv", "B", 9)
        pdf.set_text_color(*NAVY)
        pdf.cell(W * 0.24, 5, v, align="R", new_x="LMARGIN", new_y="NEXT")
    pdf.set_y(max(end_left, pdf.get_y()) + 5)

    # Buyer
    pdf.set_font("dv", "B", 9)
    pdf.cell(W, 5, "Bill to", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("dv", "", 9)
    buyer = [inv.buyer_name or inv.buyer_email]
    if inv.buyer_address:
        buyer.append(inv.buyer_address)
    buyer.append(f"State: {STATES.get(inv.buyer_state, '')} ({inv.buyer_state})")
    buyer.append(f"GSTIN: {inv.buyer_gstin}" if inv.buyer_gstin else "Unregistered (B2C)")
    buyer.append(inv.buyer_email)
    pdf.multi_cell(W, 4.6, "\n".join(buyer), align="L", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(6)

    # Line table
    cols = [("Description", 0.52, "L"), ("SAC", 0.13, "C"), ("Qty", 0.08, "C"), ("Taxable value", 0.27, "R")]
    pdf.set_fill_color(244, 246, 251)
    pdf.set_font("dv", "B", 9)
    for t, w, a in cols:
        pdf.cell(W * w, 8, t, align=a, fill=True)
    pdf.ln(8)
    pdf.set_font("dv", "", 9)
    desc = (f"AiWazz {plan_name} plan ({inv.period}), AI text-to-speech subscription\n"
            f"Service period: {_d(inv.period_start)} to {_d(inv.period_end)}")
    if cn:
        desc = (f"{'Refund' if cn.kind == 'refund' else 'Cancellation'} against invoice {inv.number}\n"
                f"Reason: {cn.reason}\n" + desc)
    x0, y0 = pdf.get_x(), pdf.get_y() + 1.5
    pdf.set_xy(x0, y0)
    pdf.multi_cell(W * 0.5, 5, desc, align="L", new_x="LMARGIN", new_y="NEXT")
    y_end = pdf.get_y()
    pdf.set_xy(x0 + W * 0.52, y0)
    pdf.cell(W * 0.13, 5, sac, align="C")
    pdf.cell(W * 0.08, 5, "1", align="C")
    pdf.cell(W * 0.27, 5, rupees(doc.taxable_paise), align="R")
    pdf.set_y(y_end + 3)
    pdf.set_draw_color(226, 232, 240)
    pdf.line(18, pdf.get_y(), 18 + W, pdf.get_y())
    pdf.ln(3)

    # Totals
    rows = [("Taxable value", rupees(doc.taxable_paise))]
    if doc.igst_paise:
        rows.append((f"IGST @ {GST_RATE}%", rupees(doc.igst_paise)))
    else:
        rows += [(f"CGST @ {GST_RATE / 2:g}%", rupees(doc.cgst_paise)), (f"SGST @ {GST_RATE / 2:g}%", rupees(doc.sgst_paise))]
    for k, v in rows:
        pdf.set_x(18 + W * 0.5)
        pdf.cell(W * 0.25, 6, k)
        pdf.cell(W * 0.25, 6, v, align="R", new_x="LMARGIN", new_y="NEXT")
    pdf.set_x(18 + W * 0.5)
    pdf.set_font("dv", "B", 11)
    pdf.cell(W * 0.25, 9, "Total credited" if cn else "Total paid")
    pdf.cell(W * 0.25, 9, rupees(doc.total_paise), align="R", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(8)

    pdf.set_font("dv", "", 8)
    pdf.set_text_color(*MUTED)
    first = ("Refunds go back to the original payment method through Razorpay. " if cn else "Paid online through Razorpay. ") + \
        f"This is a computer-generated {'credit note' if cn else 'invoice'} and needs no signature.\n"
    pdf.multi_cell(W, 4.2, align="L", text=first +
                           f"Questions about this invoice: {LEGAL.get('supportEmail', '')}", new_x="LMARGIN", new_y="NEXT")
    path.parent.mkdir(parents=True, exist_ok=True)
    pdf.output(str(path))
    return path
