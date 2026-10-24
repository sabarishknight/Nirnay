"""D5 research note, D6 AI usage log and the presenter pack as PDFs (also served from /static/docs)."""
import os
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, ListFlowable, ListItem, KeepTogether
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "web", "static", "docs")
os.makedirs(OUT, exist_ok=True)

# fonts with the rupee sign
F, FB = "Helvetica", "Helvetica-Bold"
for reg, bold in [("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
                  ("/usr/share/fonts/truetype/noto/NotoSans-Regular.ttf", "/usr/share/fonts/truetype/noto/NotoSans-Bold.ttf")]:
    if os.path.exists(reg) and os.path.exists(bold):
        pdfmetrics.registerFont(TTFont("Body", reg)); pdfmetrics.registerFont(TTFont("BodyB", bold))
        pdfmetrics.registerFontFamily("Body", normal="Body", bold="BodyB", italic="Body", boldItalic="BodyB")
        F, FB = "Body", "BodyB"
        break

NAVY = colors.HexColor("#173a5e")
T = ParagraphStyle("t", fontName=FB, fontSize=15, leading=19, textColor=colors.HexColor("#18212b"), spaceAfter=2)
SUB = ParagraphStyle("sub", fontName=F, fontSize=8.5, leading=11, textColor=colors.HexColor("#6b7480"), spaceAfter=6)
H = ParagraphStyle("h", fontName=FB, fontSize=10.5, leading=13, textColor=NAVY, spaceBefore=7, spaceAfter=3)
B = ParagraphStyle("b", fontName=F, fontSize=8.6, leading=11.6, textColor=colors.HexColor("#26303b"))
SM = ParagraphStyle("sm", parent=B, fontSize=7.6, leading=10)
BOX = ParagraphStyle("box", parent=B, backColor=colors.HexColor("#e9eff6"), borderPadding=(5, 6, 5, 6), spaceBefore=4, spaceAfter=6)


def bullets(items, style=B):
    return ListFlowable([ListItem(Paragraph(i, style), leftIndent=10, value="•") for i in items], bulletType="bullet", start="•", leftIndent=10, bulletFontSize=7, spaceBefore=0, spaceAfter=2)


def table(rows, widths, style=SM, head=True):
    t = Table([[Paragraph(str(c), ParagraphStyle("c", parent=style, fontName=FB if (head and i == 0) else style.fontName)) for c in r] for i, r in enumerate(rows)], colWidths=widths)
    t.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LINEBELOW", (0, 0), (-1, -1), 0.3, colors.HexColor("#dce1e6")),
                           ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f2f4f6") if head else colors.white),
                           ("TOPPADDING", (0, 0), (-1, -1), 2.5), ("BOTTOMPADDING", (0, 0), (-1, -1), 2.5), ("LEFTPADDING", (0, 0), (-1, -1), 3)]))
    return t


def doc(name, story):
    d = SimpleDocTemplate(os.path.join(OUT, name), pagesize=A4, leftMargin=15 * mm, rightMargin=15 * mm, topMargin=13 * mm, bottomMargin=12 * mm,
                          title=name.replace("_", " ").replace(".pdf", ""), author="Presales BA candidate")
    d.build(story)


W = A4[0] - 30 * mm

# =============================================================================================== D5
d5 = [Paragraph("How a home loan is approved in an Indian bank", T),
      Paragraph("D5 research note for the Nirnay point-of-view demo. Audience: Retail Lending head, mid-sized Indian bank. October 2026.", SUB),
      Paragraph("<b>In short.</b> A home loan passes through seven stages and at least six roles. Credit appraisal is judgement applied to data gathered from many places; legal and technical verification is the longest stage and stays human. The largest gains come from assembling the file at login, checking documents against independent sources, and applying policy identically on every file.", BOX),
      Paragraph("1. Stages, roles and checks", H),
      table([["Stage", "What happens", "Who", "Typical time"],
             ["Sourcing and login", "Application, KYC, income and property papers; file opened in the LOS; login fee", "RM, DSA, builder tie-up, online", "0 to 2 days"],
             ["KYC and de-dupe", "PAN, Aadhaar/OVD, CKYC; internal de-dupe and negative lists; field investigation of residence and office", "Operations, FI agency", "1 to 3 days"],
             ["Credit appraisal", "Bureau report; income from slips, Form 16, bank statements or ITR/GST; FOIR, eligibility, risk grade; appraisal note", "Credit processing officer, credit manager", "3 to 7 days"],
             ["Legal and technical", "Title search (13 to 30 years), encumbrance certificate, CERSAI search; site visit and valuation; RCU document sampling", "Panel advocate, empanelled valuer, RCU", "5 to 12 days (longest)"],
             ["Sanction", "Approval per delegation of financial powers; deviations escalate; sanction letter and Key Facts Statement", "BCM, regional credit head, committee", "1 to 4 days"],
             ["Documentation", "Agreement; mortgage by deposit of title deeds or registration; tripartite for under-construction; CERSAI registration within 30 days", "Operations, legal", "3 to 8 days"],
             ["Disbursement", "Payment to seller or builder; stage-linked tranches; EMI or pre-EMI starts", "Operations", "1 to 3 days"]],
            [28 * mm, 82 * mm, 42 * mm, W - 152 * mm]),
      Paragraph("Lenders quote 7 to 15 working days to sanction and up to about 30 days to disbursement, faster for salaried applicants and slower for self-employed applicants and resale properties (Kotak). The demo's synthetic book averages about 18 working days to sanction, typical of manual appraisal at a mid-sized bank.", B),
      Paragraph("2. Rules that shape the process", H),
      bullets(["<b>LTV caps</b>: 90% up to ₹30 lakh, 80% to ₹75 lakh, 75% above; stamp duty excluded except for units up to ₹10 lakh. Risk weight 35% up to 80% LTV, 50% above (RBI, 16 Oct 2020).",
               "<b>External benchmark pricing</b>: floating retail loans linked to an external benchmark such as repo, reset at least quarterly (RBI, 4 Sep 2019). Repo rose 5.25% to 5.50% on 7 Oct 2026.",
               "<b>Key Facts Statement</b> with all-in APR for every retail loan from 1 Oct 2024 (RBI, 15 Apr 2024).",
               "<b>CERSAI</b>: register security interests within 30 days; search before sanction (SARFAESI s.23).",
               "<b>Release of documents</b> within 30 days of closure or ₹5,000 a day compensation (RBI, 13 Sep 2023).",
               "<b>No pre-payment charges</b> on floating-rate loans to individuals for non-business purposes, loans from 1 Jan 2026 (RBI directions, 2 Jul 2025).",
               "<b>KYC Master Direction</b> (CKYCR, V-CIP); written rejection reasons (Fair Practices Code); DPDP Act 2023 and Account Aggregator consent."]),
      Paragraph("3. Pain points", H),
      bullets(["<b>Chasing and re-keying</b>: data gathered from the LOS, core banking, portals and PDFs and re-typed into the appraisal note.",
               "<b>Legal and technical is the long pole</b> and starts late because the file is incomplete at login.",
               "<b>Inconsistency</b>: FOIR and eligibility computed in personal spreadsheets; branches differ on the same facts.",
               "<b>Fraud</b>: inflated salary slips, forged or duplicate title deeds, multiple financing of one property (RBI and NHB advisories).",
               "<b>Policy drift</b>: rate or rule changes apply to new files only; in-flight files keep stale assessments.",
               "<b>Customer opacity</b>: applicants do not know the stage or what is missing."]),
      Paragraph("4. Implications for the solution", H),
      bullets(["Assemble the whole file in a lakehouse at login so legal and technical can start on day one.",
               "AI reads documents and drafts; rules and arithmetic run in code and cite the clause; people decide.",
               "Cross-check documents against bank credits, Form 16, EPFO, GST and CERSAI, where fraud shows up.",
               "Keep decisions with the delegation of powers; make overrides easy, recorded and reviewed.",
               "Store policy as data so a change can be re-applied to files in progress."]),
      Paragraph("5. How these findings were checked, and what to test with practitioners", H),
      Paragraph("Every rule above was checked against the RBI circular itself, not a summary; turnaround ranges come from lender disclosures. No interviews with banking practitioners were held before submission. Before the walkthrough I will test three claims with credit staff: (1) legal and technical is the longest stage; (2) FOIR deviations are the most common reason a file goes to a higher authority; (3) officers would accept a drafted note for sanction if every line shows its source. The 15-minute interview guide is ready.", B),
      Paragraph("Sources", H),
      Paragraph("RBI/2020-21/56 Individual Housing Loans: Rationalisation of Risk Weights (rbi.org.in, Id=11984); KS&amp;K, Consolidation of housing finance rules (ksandk.com); RBI/2019-20/53 External Benchmark Based Lending (Id=11677); RBI KFS for Loans &amp; Advances (Id=12663) and Vinod Kothari commentary; RBI Release of Property Documents (Id=12535); Business Standard on pre-payment directions (2 Jul 2025); RBI KYC Master Direction 2016; SCC Online, repo hike to 5.50% (9 Oct 2026); ClearTax and Kotak on CERSAI; Kotak, Home loan processing time; NHB, Fraudulent transactions in housing finance. Full links at /research in the demo.", SM)]
doc("D5_research_note.pdf", d5)

# =============================================================================================== D6
d6 = [Paragraph("AI usage log", T),
      Paragraph("D6 for the Nirnay demo. How Claude was used, what worked, what was corrected, and the time saved.", SUB),
      Paragraph("Tools", H),
      Paragraph("<b>Claude</b> (Claude app with an agent workspace built on Claude Code: web search, code execution, file tools) for research, data generation, coding, interface design, testing with screenshots, writing and deployment. <b>Gemini on Vertex AI</b> runs inside the product to read documents and draft notes.", B),
      Paragraph("How the work ran", H),
      table([["Stage", "Key prompt or instruction", "What Claude produced"],
             ["Brief analysis", "\"Go through the document thoroughly… how do you see it as an analyst?\"", "Deliverables map, scoring weights (60 of 100 points on research, story and AI use), product recommendation (home loan) and differentiators"],
             ["Research", "Verify RBI rules, CERSAI, KFS, turnaround; use current repo rate", "Searches and fetches of RBI and secondary sources; clause pack with verified links; research note"],
             ["Data", "Realistic Indian book: 200 to 1,000 applicants, accounts, loans, repayments", "Seeded generator: 600 applications, bureau, CERSAI, KYC, AA, EPFO, GST; four scripted demo files with PDF documents"],
             ["Lakehouse, agent, app", "One well-designed agent; explainable; human in the loop", "Raw, curated, gold SQL tested locally then run in BigQuery; seven-step agent, rules with clause ids, Gemini document reading and note drafting, Policy Watch"],
             ["Interface", "\"Simple, professional, not AI-looking\"", "Ledger-style UI; reviewed through screenshots after each pass"],
             ["Deploy", "\"Give me the code to run it in my Google Cloud project\"", "One-command deploy script, run from my own terminal: BigQuery in Mumbai, service account, Gemini model check, Cloud Run"],
             ["Hand-over and QA", "\"Check the status, what is pending, and help me finish\"", "A second Claude session audited the first one's output, re-ran all four demo files, found the open items and wrote the README"]],
            [24 * mm, 62 * mm, W - 86 * mm]),
      Paragraph("What I corrected (with Claude)", H),
      bullets(["<b>Wrong citation and guessed links</b>: the first draft credited LTV caps to the RBI 2020 circular, which sets risk weights only; and early RBI links were guessed IDs. Each was checked against the source and fixed.",
               "<b>Unrealistic data</b>: the first book put 72 of 146 in-flight files outside policy. Rebalanced to a realistic mix and seeded borderline files so the repo-hike story is real, not scripted.",
               "<b>Silent bugs</b>: colliding property IDs gave 606 rows for 600 applications (caught by a row-count check); a field-name clash made GST look missing (caught in a screenshot review).",
               "<b>Platform limits</b>: the build workspace could not reach Google Cloud, and it was unclear which Gemini models serve India. Solved with plain REST clients, a deploy-time model probe and a fallback chain, and by deploying from my own terminal.",
               "<b>First deploy failed</b>: I ran the commands with placeholder IDs still in them. Claude read the error log, gave corrected commands with my real organisation and billing IDs, and the second run went live.",
               "<b>Wrong inputs caught</b>: five JSON files I thought were project outputs turned out to be unrelated health-claim extracts. Claude flagged them before they went anywhere near the submission."]),
      Paragraph("What worked, and what needed steering", H),
      Paragraph("Asking for evidence (circular text, row counts, screenshots) instead of accepting first answers worked best. First drafts of copy were wordier than a banker would read, and story-page numbers had to be re-synced with live query results.", B),
      Paragraph("Time saved (estimate)", H),
      table([["Work", "Without AI", "With Claude"],
             ["Research and note", "1.5 days", "2 hours, plus my review"],
             ["Synthetic data and documents", "1.5 days", "1 hour"],
             ["Backend, agent, SQL", "2 days", "2 hours"],
             ["Interface (11 pages)", "2 days", "2 hours"],
             ["Total", "About 7 working days", "About 1 day elapsed"]], [60 * mm, 50 * mm, W - 110 * mm]),
      Paragraph("My reflection", H),
      Paragraph("Claude proposed most of the build; my job was direction and judgement. I chose the home loan product and the India focus, and pushed for a plain banking interface rather than an AI showcase. When the reference demo turned out to be a knowledge-graph explorer, I asked whether to copy it; we decided not to, because its job is policy search while ours is a loan decision. The biggest lesson was to verify rather than trust: Claude was fast, but the wrong citation, the duplicate rows and the unrelated JSON files were all found by checking. Next time I would talk to bankers in the first two days, not the last, and set up the cloud project before the build.", B)]
doc("D6_ai_usage_log.pdf", d6)

# =============================================================================================== presenter pack
pp = [Paragraph("Presenter pack", T), Paragraph("Walkthrough script, 5-minute recording, likely questions, and the practitioner interview guide. For your use; not part of the site navigation.", SUB),
      Paragraph("20-minute walkthrough", H),
      table([["Min", "Show", "Say"],
             ["0-2", "Overview page", "The problem in their words: 18 working days, nine systems, officers re-keying. Our point of view: lakehouse first, one agent, people decide."],
             ["2-5", "Approach story", "Act 1: three layers, one version of the customer. Act 2: seven steps, what stays human. The value table and its assumptions."],
             ["5-11", "Officer desk: Priya, then Arjun", "Run Priya: documents read, parallel checks, 14 checks with clauses, note drafted, sanction stamp. Then Arjun: repo hike pushed FOIR to 55.5%; three ways back within policy; refer, then approve as Regional Credit Head."],
             ["11-13", "Sunita and Vikram (results only)", "Contradictions surface on day one: CERSAI vs seller's declaration; payslip vs bank credits goes to RCU as a check, not an accusation."],
             ["13-16", "Lending head", "Policy Watch on the 7 Oct repo hike: 15 files now outside policy, ₹9.5 crore. Override patterns as the learning loop."],
             ["16-19", "Architecture", "Business to technical mapping; what is real vs simulated; data stays in Mumbai region."],
             ["19-20", "Story page, pilot", "Six-week pilot: shadow mode first. Ask for their numbers (the five discovery questions on the overview page)."]],
            [12 * mm, 38 * mm, W - 50 * mm]),
      Paragraph("5-minute recording", H),
      bullets(["0:00 Overview, one sentence on the problem and the approach.", "0:30 Officer desk: run Arjun Mehta live; pause on the FOIR row and the options.", "2:30 Note for sanction; refer; approve as authority; show the stamp.", "3:15 Lending head: run Policy Watch.", "4:00 Architecture page, then close on the pilot."]),
      Paragraph("Likely questions", H),
      bullets(["<b>What if Gemini misreads a document?</b> Decision figures come from independent sources (AA, bureau, valuer); documents are cross-checks; officer sees fields beside the PDF.",
               "<b>Hallucination in the note?</b> Drafted only from verified facts with clause citations; editable; the officer's version is recorded.",
               "<b>Why not many agents?</b> Appraisal is a fixed sequence; one agent is easier to test, audit and explain; parallel only where independent.",
               "<b>Data residency and DPDP?</b> BigQuery and Cloud Run in Mumbai; consent records; least privilege; VPC-SC and CMEK in production.",
               "<b>Bias?</b> No protected attributes in rules; overrides and outcomes monitored by segment.",
               "<b>Integration?</b> Datastream CDC from core banking and LOS; desk embeds in the LOS.",
               "<b>How do you know 8.5 days?</b> It is an estimate with stated assumptions; the pilot measures it."]),
      Paragraph("Practitioner interview guide (15 minutes)", H),
      bullets(["Walk me through your last home loan file: where did it wait longest?", "What do you check by hand that you wish a system checked?",
               "How often do files go on deviation, and for what?", "What fraud patterns does RCU find most?", "Would you trust a drafted note for sanction? What would make you trust it?",
               "Does the 7 to 15 day sanction range match your bank?"])]
doc("presenter_pack.pdf", pp)
print("ok", F)
