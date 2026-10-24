"""Creates the applicant documents for the four demo cases as PDFs plus ground-truth fields.

web/static/docs/<application_id>/<doc_key>.pdf  -> shown in the UI and sent to Gemini for reading
data/out/hero_docs.json                         -> {application_id: [{doc_key, doc_type, file, fields, text}]}
Ground-truth fields are used when Gemini is not reachable (offline demo mode).
"""
import json, os
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
H = json.load(open(os.path.join(ROOT, "data", "out", "heroes.json")))
OUTDIR = os.path.join(ROOT, "web", "static", "docs")
ss = getSampleStyleSheet()
T = ParagraphStyle("t", parent=ss["Title"], fontName="Helvetica-Bold", fontSize=14, alignment=0, spaceAfter=2)
S = ParagraphStyle("s", parent=ss["Normal"], fontName="Helvetica", fontSize=8.5, textColor=colors.HexColor("#555555"))
B = ParagraphStyle("b", parent=ss["Normal"], fontName="Helvetica", fontSize=9.5, leading=13)


def inr(x):
    x = int(round(x))
    s = str(abs(x))
    if len(s) > 3:
        head, tail = s[:-3], s[-3:]
        parts = []
        while len(head) > 2:
            parts.insert(0, head[-2:])
            head = head[:-2]
        if head:
            parts.insert(0, head)
        s = ",".join(parts) + "," + tail
    return ("-" if x < 0 else "") + "Rs " + s


def pdf(path, issuer, sub, title, rows, notes=None, footer_rows=None):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    doc = SimpleDocTemplate(path, pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm, topMargin=16 * mm, bottomMargin=16 * mm)
    el = [Paragraph(issuer, T), Paragraph(sub, S), Spacer(1, 8), Paragraph(f"<b>{title}</b>", B), Spacer(1, 6)]
    t = Table(rows, colWidths=[62 * mm, 108 * mm] if len(rows[0]) == 2 else None)
    t.setStyle(TableStyle([("FONT", (0, 0), (-1, -1), "Helvetica", 9), ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#BBBBBB")),
                           ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#F2F2F2")) if len(rows[0]) == 2 else ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#F2F2F2")),
                           ("VALIGN", (0, 0), (-1, -1), "TOP"), ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4)]))
    el.append(t)
    if footer_rows:
        el += [Spacer(1, 8)]
        t2 = Table(footer_rows)
        t2.setStyle(TableStyle([("FONT", (0, 0), (-1, -1), "Helvetica", 9), ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#BBBBBB")), ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#F2F2F2"))]))
        el.append(t2)
    for n in notes or []:
        el += [Spacer(1, 6), Paragraph(n, B)]
    el += [Spacer(1, 18), Paragraph("Synthetic specimen created for a product demonstration. Not a real document; all names and numbers are fictional.", S)]
    doc.build(el)


DOCS = {}


def add(app_id, key, doc_type, issuer, sub, title, fields, rows=None, notes=None, footer_rows=None):
    path = os.path.join(OUTDIR, app_id, key + ".pdf")
    rows = rows or [[k, str(v)] for k, v in fields.items()]
    pdf(path, issuer, sub, title, rows, notes, footer_rows)
    text = "\n".join(f"{r[0]}: {r[1]}" for r in rows if len(r) == 2) + ("\n" + "\n".join(notes) if notes else "")
    DOCS.setdefault(app_id, []).append(dict(doc_key=key, doc_type=doc_type, file=f"/static/docs/{app_id}/{key}.pdf", fields=fields, text=text))


# ------------------------------------------------------------------ Priya
a = H["priya"]["app"]["application_id"]
add(a, "salary_slip", "Salary slip (3 months)", "Kestrel Infotech Ltd", "Hinjewadi Phase 1, Pune 411057 | Payroll", "Payslip - August to October 2026 (3 months)",
    {"employee_name": "Priya Raghavan", "employee_id": "KI-20817", "designation": "Senior Software Engineer", "pan": "BQRPR4821K",
     "gross_monthly": 198500, "deductions_monthly": 56300, "net_monthly_avg_3m": 142117, "months": "Aug, Sep, Oct 2026"},
    rows=[["Employee", "Priya Raghavan (KI-20817)"], ["Designation", "Senior Software Engineer"], ["PAN", "BQRPR4821K"], ["UAN", H["priya"]["cust"]["uan"]]],
    footer_rows=[["Month", "Gross", "PF", "Prof. tax", "TDS", "Net pay"],
                 ["Aug 2026", "Rs 1,98,500", "Rs 9,360", "Rs 200", "Rs 46,790", "Rs 1,42,150"],
                 ["Sep 2026", "Rs 1,98,500", "Rs 9,360", "Rs 200", "Rs 47,040", "Rs 1,41,900"],
                 ["Oct 2026", "Rs 1,98,500", "Rs 9,360", "Rs 200", "Rs 46,640", "Rs 1,42,300"]])
add(a, "form16", "Form 16 (2 years)", "Form 16 Part B (extract)", "Certificate under section 203 of the Income-tax Act, 1961", "FY 2025-26 (AY 2026-27)",
    {"employer": "Kestrel Infotech Ltd", "tan": "PNEK01234E", "employee": "Priya Raghavan", "pan": "BQRPR4821K", "gross_salary_annual": 2310000, "tax_deducted_annual": 512400, "net_after_tax_monthly_equiv": 149800})
add(a, "bank_statement", "Bank statement (6 months)", "Bank statement summary", "Savings account SB-****4471 | Generated from core banking", "May to October 2026",
    {"account_holder": "Priya Raghavan", "avg_monthly_salary_credit": 142300, "salary_credits_found": 6, "emi_debits": "Car loan Rs 14,500 monthly", "cheque_bounces": 0, "avg_eod_balance": 402000})
add(a, "allotment", "Sale agreement / allotment letter", "Aaranya Developers", "RERA registration RERA-PUN-52118 | Aaranya Courtyard, Hinjewadi Phase 2", "Allotment letter and agreement for sale",
    {"buyer": "Priya Raghavan", "unit": "Tower B, Flat 1104", "carpet_area_sqft": 1085, "agreement_value": 9200000, "stamp_duty_and_registration": 640000,
     "rera_number": "RERA-PUN-52118", "construction_stage": "9th-floor slab, 62% complete", "possession_date": "June 2028"})

# ------------------------------------------------------------------ Arjun
a = H["arjun"]["app"]["application_id"]
add(a, "itr", "ITR with computation (2 years)", "Income Tax Return acknowledgement (ITR-V) with computation", "Arjun Mehta | PAN AKZPM7712D | Proprietor, Mehta Packaging", "AY 2025-26 and AY 2026-27",
    {"name": "Arjun Mehta", "pan": "AKZPM7712D", "business": "Mehta Packaging (proprietorship)", "income_after_tax_fy2024_25": 1102000, "income_after_tax_fy2025_26": 1197000,
     "depreciation_fy2024_25": 26000, "depreciation_fy2025_26": 27000, "turnover_fy2025_26": 7940000, "assessed_monthly_income": 98000},
    rows=[["Name / PAN", "Arjun Mehta / AKZPM7712D"], ["Business", "Mehta Packaging (proprietorship), Ahmedabad"]],
    footer_rows=[["Item", "FY 2024-25", "FY 2025-26"], ["Turnover", "Rs 71,20,000", "Rs 79,40,000"], ["Income after tax", "Rs 11,02,000", "Rs 11,97,000"],
                 ["Add: depreciation", "Rs 26,000", "Rs 27,000"], ["Cash income", "Rs 11,28,000", "Rs 12,24,000"]],
    notes=["Average cash income over 2 years: Rs 11,76,000 a year, i.e. Rs 98,000 a month."])
add(a, "gst", "GST returns (12 months)", "GST return filing summary (GSTR-3B)", "GSTIN 24AKZPM7712D1Z5 | Mehta Packaging", "October 2025 to September 2026",
    {"gstin": "24AKZPM7712D1Z5", "turnover_12m": 8160000, "returns_filed": 12, "returns_filed_late": 1, "status": "Active"})
add(a, "bank_statement", "Bank statement (12 months)", "Bank statement summary", "Current account CA-****0912 and savings SB-****3318", "October 2025 to September 2026",
    {"account_holder": "Arjun Mehta / Mehta Packaging", "avg_monthly_credits_current_account": 690000, "avg_monthly_credits_savings": 98000, "emi_debits": "Car loan Rs 6,150 monthly", "cheque_bounces": 0})
add(a, "sale_agreement", "Sale agreement / allotment letter", "Agreement for sale (draft)", "Shantivan Apartments Co-op Housing Society, Satellite Road, Ahmedabad", "Resale of Flat 7B",
    {"buyer": "Arjun Mehta", "co_owner_on_title": "None (sole purchaser)", "seller": "Hemant Joshi", "unit": "Flat 7B, Shantivan Apartments", "carpet_area_sqft": 1240,
     "agreement_value": 7400000, "society_noc": "Issued 28 Sep 2026"})
add(a, "spouse_salary", "Co-applicant salary slip", "Directorate of Primary Education, Gujarat", "Pay slip | Kavya Mehta, Assistant Teacher", "September 2026",
    {"employee_name": "Kavya Mehta", "employer": "Govt. of Gujarat (Education)", "net_monthly": 38200, "gross_monthly": 52600})

# ------------------------------------------------------------------ Sunita
a = H["sunita"]["app"]["application_id"]
add(a, "salary_slip", "Salary slip (3 months)", "Basic Education Department, Uttar Pradesh", "Salary statement | Sunita Yadav, Assistant Teacher", "August to October 2026",
    {"employee_name": "Sunita Yadav", "employer": "Govt. of Uttar Pradesh (Basic Education)", "net_monthly_avg_3m": 71500, "gross_monthly": 89200})
add(a, "co_salary_slip", "Co-applicant salary slip", "Pinecrest Logistics Pvt Ltd", "Payslip | Rakesh Yadav, Operations Supervisor", "August to October 2026",
    {"employee_name": "Rakesh Yadav", "employer": "Pinecrest Logistics Pvt Ltd", "net_monthly_avg_3m": 46000, "gross_monthly": 54800})
add(a, "sale_deed_draft", "Sale agreement / allotment letter", "Agreement to sell (registered)", "Sub-Registrar office, Lucknow", "House 214, Sector 11, Indira Nagar",
    {"buyers": "Sunita Yadav and Rakesh Yadav (joint)", "seller": "Om Prakash Srivastava", "agreement_value": 5200000, "plot_area_sqft": 1450,
     "seller_declaration": "Property free from all encumbrances; earlier housing loan from Gomti Housing Finance Ltd fully repaid in March 2025"})
add(a, "encumbrance", "Encumbrance certificate", "Encumbrance certificate (extract)", "Office of the Sub-Registrar, Lucknow | 30-year search 1996-2026", "House 214, Sector 11, Indira Nagar",
    {"period": "1996 to 2026", "entry_1": "2011: Sale deed in favour of Om Prakash Srivastava", "entry_2": "2019: Memorandum of deposit of title deeds in favour of Gomti Housing Finance Ltd, Rs 29,00,000",
     "release_recorded": "No release deed or memorandum of release recorded"})

# ------------------------------------------------------------------ Vikram
a = H["vikram"]["app"]["application_id"]
add(a, "salary_slip", "Salary slip (3 months)", "Meghdoot Retail Pvt Ltd", "Sector 44, Gurugram | Payroll", "Payslip - August to October 2026 (3 months)",
    {"employee_name": "Vikram Sethi", "designation": "Area Sales Manager", "gross_monthly": 171000, "net_monthly_avg_3m": 135000, "months": "Aug, Sep, Oct 2026"},
    rows=[["Employee", "Vikram Sethi (MR-4410)"], ["Designation", "Area Sales Manager"], ["PAN", "DNSPS6604R"]],
    footer_rows=[["Month", "Gross", "PF", "TDS", "Net pay"], ["Aug 2026", "Rs 1,71,000", "Rs 5,580", "Rs 30,420", "Rs 1,35,000"],
                 ["Sep 2026", "Rs 1,71,000", "Rs 5,580", "Rs 30,420", "Rs 1,35,000"], ["Oct 2026", "Rs 1,71,000", "Rs 5,580", "Rs 30,420", "Rs 1,35,000"]])
add(a, "form16", "Form 16 (2 years)", "Form 16 Part B (extract)", "Certificate under section 203 of the Income-tax Act, 1961", "FY 2025-26 (AY 2026-27)",
    {"employer": "Meghdoot Retail Pvt Ltd", "employee": "Vikram Sethi", "pan": "DNSPS6604R", "gross_salary_annual": 1320000, "tax_deducted_annual": 118600, "net_after_tax_monthly_equiv": 100100})
add(a, "bank_statement", "Bank statement (6 months)", "Bank statement summary", "Savings account SB-****2290", "May to October 2026",
    {"account_holder": "Vikram Sethi", "avg_monthly_salary_credit": 88400, "salary_credits_found": 6, "salary_credit_narration": "NEFT MEGHDOOT RETAIL SAL", "emi_debits": "Personal loan Rs 11,800 monthly", "cheque_bounces": 0})
add(a, "sale_agreement", "Sale agreement / allotment letter", "Agreement for sale", "Silver Oaks, Sector 49, Gurugram", "Resale of Flat 603",
    {"buyer": "Vikram Sethi", "seller": "Neeraj Arora", "agreement_value": 8900000, "carpet_area_sqft": 960, "occupation_certificate": "Available (2020)"})

# ------------------------------------------------------------------ credit policy as a document
import sys  # noqa: E402
sys.path.insert(0, os.path.join(ROOT, "app"))
from policy_pack import CLAUSES  # noqa: E402

pol = os.path.join(OUTDIR, "policy", "home_loan_credit_policy_v4_2.pdf")
os.makedirs(os.path.dirname(pol), exist_ok=True)
d = SimpleDocTemplate(pol, pagesize=A4, leftMargin=20 * mm, rightMargin=20 * mm, topMargin=18 * mm, bottomMargin=18 * mm)
el = [Paragraph("Home Loan Credit Policy v4.2", T), Paragraph("Retail Lending | Illustrative policy written for this demonstration, not any bank's actual policy", S), Spacer(1, 10)]
for c in CLAUSES:
    el += [Paragraph(f"<b>{c['clause_id']}  {c['title']}</b>  <font color='#666666' size='8'>{c['document']}</font>", B), Paragraph(c["text"], B), Spacer(1, 7)]
d.build(el)

json.dump(DOCS, open(os.path.join(ROOT, "data", "out", "hero_docs.json"), "w"), indent=1)
print({k: len(v) for k, v in DOCS.items()})
