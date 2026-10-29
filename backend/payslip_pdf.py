"""Payslip PDF rendering (ReportLab). No database or FastAPI imports, so it is easy to test.

The rupee sign (U+20B9) is missing from ReportLab's built-in fonts - it would
print as a black box. We therefore try to register a system TrueType font that
has it (DejaVu Sans, Arial, ...) and fall back to the text "Rs." if none is found.
"""
import os
from decimal import Decimal
from io import BytesIO

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from payroll_engine import q2

_FONT_CANDIDATES = [
    ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
    ("/usr/share/fonts/dejavu/DejaVuSans.ttf", "/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf"),
    ("/Library/Fonts/Arial Unicode.ttf", "/Library/Fonts/Arial Unicode.ttf"),
    ("C:\\Windows\\Fonts\\arial.ttf", "C:\\Windows\\Fonts\\arialbd.ttf"),
    ("C:\\Windows\\Fonts\\segoeui.ttf", "C:\\Windows\\Fonts\\segoeuib.ttf"),
]
_FONTS = None  # (regular, bold, rupee_symbol) resolved once


def _resolve_fonts():
    global _FONTS
    if _FONTS:
        return _FONTS
    custom = os.getenv("PAYSLIP_FONT_PATH")           # optional: path to a .ttf that has the rupee sign
    candidates = ([(custom, custom)] if custom else []) + _FONT_CANDIDATES
    for regular, bold in candidates:
        if os.path.exists(regular) and os.path.exists(bold):
            try:
                pdfmetrics.registerFont(TTFont("VertexSans", regular))
                pdfmetrics.registerFont(TTFont("VertexSans-Bold", bold))
                _FONTS = ("VertexSans", "VertexSans-Bold", "\u20b9")
                return _FONTS
            except Exception:                          # unreadable font file - try the next one
                continue
    _FONTS = ("Helvetica", "Helvetica-Bold", "Rs.")
    return _FONTS


def format_inr(amount) -> str:
    """Indian digit grouping: 1234567.5 -> '12,34,567.50'."""
    amount = q2(Decimal(amount))
    sign = "-" if amount < 0 else ""
    whole, frac = f"{abs(amount):.2f}".split(".")
    if len(whole) > 3:
        head, tail, groups = whole[:-3], whole[-3:], []
        while len(head) > 2:
            groups.insert(0, head[-2:])
            head = head[:-2]
        if head:
            groups.insert(0, head)
        whole = ",".join(groups + [tail])
    return f"{sign}{whole}.{frac}"


def build_payslip_pdf(d: dict) -> bytes:
    """``d`` is the dict produced by payslips.payslip_detail()."""
    regular, bold, rupee = _resolve_fonts()
    money = lambda v: f"{rupee} {format_inr(v)}"
    ink, muted, accent = colors.HexColor("#0F172A"), colors.HexColor("#64748B"), colors.HexColor("#2563EB")

    h_company = ParagraphStyle("c", fontName=bold, fontSize=17, textColor=ink, leading=21)
    h_sub = ParagraphStyle("s", fontName=regular, fontSize=10, textColor=muted, leading=14)
    cell = ParagraphStyle("cell", fontName=regular, fontSize=9, textColor=ink, leading=12)
    cell_b = ParagraphStyle("cellb", parent=cell, fontName=bold)
    small = ParagraphStyle("small", fontName=regular, fontSize=8, textColor=muted, leading=11)

    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=16 * mm, rightMargin=16 * mm,
                            topMargin=14 * mm, bottomMargin=14 * mm,
                            title=f"Payslip {d['payslip_no']}", author=d["company_name"])
    comp_statutory = []
    if d.get("company_pan"): comp_statutory.append(f"PAN: {d['company_pan']}")
    if d.get("company_tan"): comp_statutory.append(f"TAN: {d['company_tan']}")
    if d.get("company_gstin"): comp_statutory.append(f"GSTIN: {d['company_gstin']}")
    statutory_str = " &nbsp;&middot;&nbsp; ".join(comp_statutory)
    address_str = d.get("company_address") or ""

    story = [
        Paragraph(d["company_name"], h_company),
    ]
    if address_str:
        story.append(Paragraph(address_str, h_sub))
    if statutory_str:
        story.append(Paragraph(statutory_str, small))
    story += [
        Spacer(1, 2 * mm),
        Paragraph(f"Payslip for <b>{d['period_label']}</b> &nbsp;&middot;&nbsp; No: <b>{d['payslip_no']}</b>", h_sub),
        Spacer(1, 5 * mm),
    ]

    emp = d["employee"]
    P = lambda text, style=cell: Paragraph(str(text if text not in (None, "") else "-"), style)
    info = [
        [P("Employee", cell_b), P(emp["name"]), P("Employee ID", cell_b), P(emp["emp_code"])],
        [P("Designation", cell_b), P(emp["designation"]), P("Department", cell_b), P(emp["department"])],
        [P("Date of joining", cell_b), P(emp["joining_date"]), P("PAN", cell_b), P(emp["pan_masked"])],
        [P("Bank", cell_b), P(f"{emp['bank_name'] or '-'} {emp['account_masked'] or ''}".strip()),
         P("UAN", cell_b), P(emp["uan_number"])],
        [P("Days paid", cell_b), P(f"{d['days']['active_days']} of {d['days']['days_in_month']}"),
         P("Loss of pay days", cell_b), P(d["days"]["lop_days"])],
    ]
    t = Table(info, colWidths=[32 * mm, 56 * mm, 32 * mm, 54 * mm])
    t.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 0.6, colors.HexColor("#CBD5E1")),
        ("INNERGRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#E2E8F0")),
        ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#F8FAFC")),
        ("BACKGROUND", (2, 0), (2, -1), colors.HexColor("#F8FAFC")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    story += [t, Spacer(1, 6 * mm)]

    earn = [(x["label"], x["amount"]) for x in d["earnings"]]
    ded = [(x["label"], x["amount"]) for x in d["deductions"]]
    rows = [[P("Earnings", cell_b), P("Amount", cell_b), P("Deductions", cell_b), P("Amount", cell_b)]]
    for i in range(max(len(earn), len(ded))):
        e = earn[i] if i < len(earn) else ("", None)
        x = ded[i] if i < len(ded) else ("", None)
        rows.append([P(e[0]), P(money(e[1]) if e[1] is not None else ""),
                     P(x[0]), P(money(x[1]) if x[1] is not None else "")])
    rows.append([P("Gross earnings", cell_b), P(money(d["gross"]), cell_b),
                 P("Total deductions", cell_b), P(money(d["total_deductions"]), cell_b)])
    amounts = TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#F1F5F9")),
        ("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#F1F5F9")),
        ("BOX", (0, 0), (-1, -1), 0.6, colors.HexColor("#CBD5E1")),
        ("LINEAFTER", (1, 0), (1, -1), 0.6, colors.HexColor("#CBD5E1")),
        ("ALIGN", (1, 0), (1, -1), "RIGHT"), ("ALIGN", (3, 0), (3, -1), "RIGHT"),
        ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ])
    t2 = Table(rows, colWidths=[48 * mm, 40 * mm, 48 * mm, 38 * mm])
    t2.setStyle(amounts)
    story += [t2, Spacer(1, 6 * mm)]

    net = Table([[P("Net pay", ParagraphStyle("n", fontName=bold, fontSize=12, textColor=colors.white)),
                  P(money(d["net"]), ParagraphStyle("nv", fontName=bold, fontSize=14, textColor=colors.white, alignment=2))]],
                colWidths=[88 * mm, 86 * mm])
    net.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), accent), ("TOPPADDING", (0, 0), (-1, -1), 8),
                             ("BOTTOMPADDING", (0, 0), (-1, -1), 8), ("VALIGN", (0, 0), (-1, -1), "MIDDLE")]))
    story += [net, Spacer(1, 2 * mm), Paragraph(d["net_words"], small), Spacer(1, 10 * mm),
              Paragraph("This is a system-generated payslip and does not require a signature. "
                        "Bank, PAN and account details are partially masked for your security.", small)]
    doc.build(story)
    return buf.getvalue()