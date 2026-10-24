"""Synthetic data generator for the Nirnay home-loan demo.

Produces a fictional mid-sized Indian bank's lending data:
  data/out/raw/*.csv      -> bronze layer, loaded into BigQuery dataset lending_raw
  world/*.json            -> what the mock external services (CIBIL, CERSAI, PAN, AA, EPFO, GST) return
  data/out/hero_docs.json -> text of applicant documents for the four scripted demo cases
All people, employers, builders, properties and identifiers are invented.
"""
import csv, json, math, os, random, datetime as dt

random.seed(20261024)
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "data", "out", "raw")
WORLD = os.path.join(ROOT, "world")
os.makedirs(OUT, exist_ok=True)
os.makedirs(WORLD, exist_ok=True)

TODAY = dt.date(2026, 10, 24)
REPO_OLD, REPO_NEW, REPO_CHANGE = 5.25, 5.50, dt.date(2026, 10, 7)
N_APPS = 600

FIRST_F = "Priya Ananya Kavya Meera Sneha Divya Pooja Neha Aishwarya Lakshmi Revathi Shalini Farah Zoya Harpreet Simran Nandini Ishita Tanvi Radhika Bhavna Gayatri Swati Rekha Deepa Anjali Sunita Madhuri Ritu Shreya".split()
FIRST_M = "Arjun Rahul Vikram Rohan Karthik Aditya Siddharth Manoj Suresh Rakesh Imran Faisal Gurpreet Harish Naveen Prakash Sanjay Amit Vivek Abhishek Nikhil Pranav Varun Kunal Deepak Ajay Ravi Srinivas Venkatesh Anil".split()
LAST = "Sharma Verma Iyer Nair Reddy Rao Patel Shah Mehta Desai Kulkarni Joshi Gupta Agarwal Singh Yadav Khan Qureshi Das Banerjee Mukherjee Ghosh Pillai Menon Chauhan Thakur Malhotra Kapoor Sethi Bhatt Pandey Mishra Tiwari Saxena Naidu Hegde Shetty Fernandes DSouza Gill".split()
CITIES = [  # city, state, pin prefix, price per sqft (INR), branch code
    ("Pune", "Maharashtra", "411", 8200, "PUN"), ("Mumbai", "Maharashtra", "400", 19500, "MUM"),
    ("Bengaluru", "Karnataka", "560", 9800, "BLR"), ("Hyderabad", "Telangana", "500", 8600, "HYD"),
    ("Chennai", "Tamil Nadu", "600", 8900, "CHE"), ("Ahmedabad", "Gujarat", "380", 6400, "AMD"),
    ("Lucknow", "Uttar Pradesh", "226", 5600, "LKO"), ("Jaipur", "Rajasthan", "302", 5200, "JAI"),
    ("Kochi", "Kerala", "682", 6900, "COK"), ("Indore", "Madhya Pradesh", "452", 4800, "IDR"),
    ("Gurugram", "Haryana", "122", 11800, "GGN"), ("Kolkata", "West Bengal", "700", 7200, "KOL"),
]
EMPLOYERS_A = ["Kestrel Infotech Ltd", "Bluefin Analytics Pvt Ltd", "Orion Pharma Ltd", "Sahyog Steel Ltd", "Northwind Consulting LLP", "Tarang Telecom Ltd"]
EMPLOYERS_B = ["Pinecrest Logistics Pvt Ltd", "Meghdoot Retail Pvt Ltd", "Vasudha Agro Foods Ltd", "Crescent Auto Components", "Lotus Hospitality Pvt Ltd"]
EMPLOYERS_GOVT = ["Govt. of Uttar Pradesh (Basic Education)", "Indian Railways", "State Electricity Board", "Municipal Corporation"]
BUSINESSES = ["Packaging", "Garments", "Pharma Distribution", "Hardware Trading", "Electrical Contracting", "Dental Clinic", "Chartered Accountancy", "Auto Spares"]
BUILDERS = ["Aaranya Developers", "Skyline Habitat", "Greenleaf Realty", "Sundaram Estates", "Mahavir Buildcon", "Coastal Homes"]
OTHER_LENDERS = ["Gomti Housing Finance Ltd", "Eastern Home Credit Ltd", "Sahyadri Urban Co-op Bank", "Pragati Housing Finance"]
CHANNELS = [("Branch", 0.38), ("DSA", 0.27), ("Builder tie-up", 0.2), ("Online", 0.15)]
STAGES = ["Login & KYC", "Credit appraisal", "Legal & technical", "Sanction", "Documentation", "Disbursed", "Declined", "Withdrawn"]
# typical working days spent in each stage today (manual process) - used to seed history
STAGE_DAYS = {"Login & KYC": (1, 3), "Credit appraisal": (3, 7), "Legal & technical": (5, 12), "Sanction": (1, 4), "Documentation": (3, 8)}
OFFICERS = ["R. Kulkarni (BCM, Pune)", "S. Iyer (BCM, Bengaluru)", "A. Khan (BCM, Lucknow)", "M. Shah (BCM, Ahmedabad)", "P. Nair (BCM, Kochi)", "V. Malhotra (BCM, Gurugram)", "D. Ghosh (BCM, Kolkata)", "K. Reddy (BCM, Hyderabad)"]


def emi(p, annual_rate, n):
    i = annual_rate / 1200
    return p * i * (1 + i) ** n / ((1 + i) ** n - 1)


def rate_for(repo, score, self_emp):
    base = repo + 2.70
    if score is None or score < 0:
        rp = 0.50
    elif score >= 775:
        rp = 0.0
    elif score >= 750:
        rp = 0.15
    elif score >= 700:
        rp = 0.35
    else:
        rp = 0.65
    return round(base + rp + (0.10 if self_emp else 0), 2)


def pan_for(name_last, kind="P"):
    letters = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    while True:
        p = _pan(name_last, kind, letters)
        if p not in USED_PANS:
            USED_PANS.add(p)
            return p


def _pan(name_last, kind, letters):
    return "".join(random.choice(letters) for _ in range(3)) + kind + name_last[0].upper() + f"{random.randint(1000, 9999)}" + random.choice(letters)


def months_back(n):
    out, y, m = [], TODAY.year, TODAY.month
    for _ in range(n):
        m -= 1
        if m == 0:
            m, y = 12, y - 1
        out.append(f"{y}-{m:02d}")
    return list(reversed(out))


MONTHS12 = months_back(12)


def rnd_date(start, end):
    return start + dt.timedelta(days=random.randint(0, (end - start).days))


def add_working_days(d, n):
    while n > 0:
        d += dt.timedelta(days=1)
        if d.weekday() < 5:
            n -= 1
    return d


def pick(weighted):
    r, acc = random.random(), 0
    for v, w in weighted:
        acc += w
        if r <= acc:
            return v
    return weighted[-1][0]


customers, accounts, loans, repayments, txns = [], [], [], [], []
apps, properties, docs, valuations, legal, stage_history = [], [], [], [], [], []
bureau, cersai, kyc, aa, epfo, gst = {}, {}, {}, {}, {}, {}
decisions = []

cust_seq, acct_seq, loan_seq, prop_seq = 100000, 500000, 700000, 3300000
USED_PANS = set()


def new_customer(**kw):
    global cust_seq
    cust_seq += 1
    cid = f"C{cust_seq}"
    gender = kw.get("gender") or random.choice("FM")
    first = kw.get("first") or random.choice(FIRST_F if gender == "F" else FIRST_M)
    last = kw.get("last") or random.choice(LAST)
    city = kw.get("city") or random.choice(CITIES)
    age = kw.get("age") or random.randint(26, 52)
    occ = kw.get("occupation") or pick([("Salaried", 0.68), ("Self-employed business", 0.22), ("Self-employed professional", 0.10)])
    if occ == "Salaried":
        cat = pick([("A", 0.45), ("B", 0.35), ("Govt", 0.2)])
        employer = kw.get("employer") or random.choice({"A": EMPLOYERS_A, "B": EMPLOYERS_B, "Govt": EMPLOYERS_GOVT}[cat])
        if kw.get("employer_category"):
            cat = kw["employer_category"]
    else:
        cat = None
        employer = kw.get("employer") or f"{last} {random.choice(BUSINESSES)}"
    c = dict(
        customer_id=cid, cif=f"CIF{random.randint(10**8, 10**9 - 1)}", full_name=f"{first} {last}", gender=gender,
        dob=(TODAY - dt.timedelta(days=age * 365 + random.randint(0, 300))).isoformat(), pan=kw.get("pan") or pan_for(last),
        aadhaar_masked=f"XXXX-XXXX-{random.randint(1000, 9999)}", mobile_masked=f"+91-XXXXXX{random.randint(1000, 9999)}",
        city=city[0], state=city[1], pincode=f"{city[2]}{random.randint(1, 99):03d}", occupation_type=occ,
        employer_name=employer, employer_category=cat or "", gstin="", uan="",
        customer_since=rnd_date(dt.date(2008, 1, 1), dt.date(2025, 6, 1)).isoformat(), home_branch=f"{city[4]}-{random.randint(1, 9):03d}",
    )
    if occ == "Salaried":
        c["uan"] = f"10{random.randint(10**9, 10**10 - 1)}"
    if occ == "Self-employed business":
        c["gstin"] = f"{random.randint(10, 36)}{c['pan']}1Z{random.randint(1, 9)}"
    customers.append(c)
    return c, city, age


def add_account(cid, kind, opened, avg_bal):
    global acct_seq
    acct_seq += 1
    a = dict(account_id=f"{kind}{acct_seq}", customer_id=cid, account_type={"SB": "Savings", "CA": "Current", "FD": "Fixed deposit"}[kind],
             open_date=opened, status="Active", avg_monthly_balance_6m=round(avg_bal), current_balance=round(avg_bal * random.uniform(0.8, 1.3)))
    accounts.append(a)
    return a


def add_existing_loan(cid, product, emi_amt, months_paid, dpd_pattern=None, lender="This bank"):
    global loan_seq
    loan_seq += 1
    lid = f"L{loan_seq}"
    tenor = {"Car loan": 60, "Personal loan": 48, "Two-wheeler loan": 36, "Business loan": 60, "Gold loan": 12, "Education loan": 84}[product]
    rate = {"Car loan": 9.1, "Personal loan": 12.5, "Two-wheeler loan": 10.5, "Business loan": 13.0, "Gold loan": 9.5, "Education loan": 10.2}[product]
    i = rate / 1200
    principal = emi_amt * ((1 + i) ** tenor - 1) / (i * (1 + i) ** tenor)
    outstanding = principal * (1 - months_paid / tenor) * 1.05
    l = dict(loan_id=lid, customer_id=cid, product=product, lender=lender, sanctioned_amount=round(principal, -3), outstanding=max(0, round(outstanding, -2)),
             emi=round(emi_amt), interest_rate=rate, start_date=(TODAY - dt.timedelta(days=30 * months_paid)).isoformat(), status="Active")
    if lender == "This bank":
        loans.append(l)
        for k, m in enumerate(MONTHS12):
            dpd = 0 if not dpd_pattern else dpd_pattern[k]
            repayments.append(dict(loan_id=lid, month=m, emi_due=l["emi"], amount_paid=l["emi"] if dpd == 0 else 0, dpd=dpd))
    return l


def monthly_txn(acct, salary, other_credit, debits, emi_total, bounces=0, salary_series=None):
    for k, m in enumerate(MONTHS12):
        sal = salary_series[k] if salary_series else (salary * random.uniform(0.98, 1.02) if salary else 0)
        credits = sal + other_credit * random.uniform(0.7, 1.3)
        deb = debits * random.uniform(0.85, 1.15) + emi_total
        txns.append(dict(account_id=acct["account_id"], month=m, total_credits=round(credits), salary_credit=round(sal), total_debits=round(deb),
                         emi_debits=round(emi_total), cheque_bounces=bounces if k == 10 else 0, closing_balance=round(acct["avg_monthly_balance_6m"] * random.uniform(0.8, 1.2))))


def bureau_report(c, score, tradelines, enquiries_90d, max_dpd_12m=0, writeoff=False):
    bureau[c["pan"]] = dict(
        pan=c["pan"], name=c["full_name"], dob=c["dob"], score=score, score_version="CIBIL TransUnion Score 3.0 (simulated)",
        report_date=TODAY.isoformat(), enquiries_last_90d=enquiries_90d, max_dpd_last_12m=max_dpd_12m, written_off_or_settled_36m=writeoff,
        accounts=[dict(member=t["lender"] if t["lender"] != "This bank" else "Reporting member (this bank)", type=t["product"], sanctioned=t["sanctioned_amount"],
                       current_balance=t["outstanding"], emi=t["emi"], opened=t["start_date"], dpd_string_12m="000|" * 11 + "000") for t in tradelines],
    )


def property_for(city, value, kind=None, under_construction=None):
    global prop_seq
    prop_seq += 1
    pid = f"P{prop_seq}"
    kind = kind or pick([("Apartment", 0.72), ("Independent house", 0.18), ("Plot + construction", 0.10)])
    uc = under_construction if under_construction is not None else (kind == "Apartment" and random.random() < 0.4)
    builder = random.choice(BUILDERS) if kind == "Apartment" else ""
    area = round(value / city[3] / 1.25)
    p = dict(property_id=pid, city=city[0], state=city[1], property_type=kind, construction_status="Under construction" if uc else "Ready / resale",
             builder=builder, project_name=f"{builder.split()[0]} {random.choice(['Residency', 'Greens', 'Heights', 'Enclave', 'Courtyard'])}" if builder else "",
             rera_number=f"RERA-{city[4]}-{random.randint(10000, 99999)}" if uc else "", carpet_area_sqft=area, agreement_value=round(value, -4),
             address=f"Flat/House {random.randint(1, 999)}, {random.choice(['Sector', 'Ward', 'Layout', 'Nagar'])} {random.randint(1, 60)}, {city[0]}", age_years=0 if uc else random.randint(2, 25))
    properties.append(p)
    return p


def stamp_docs(app_id, occ, received):
    kinds = ["PAN card", "Aadhaar (masked)", "Photograph"]
    if occ == "Salaried":
        kinds += ["Salary slip (3 months)", "Form 16 (2 years)", "Bank statement (6 months)"]
    else:
        kinds += ["ITR with computation (2 years)", "Audited financials", "GST returns (12 months)", "Bank statement (12 months)"]
    kinds += ["Sale agreement / allotment letter", "Title documents chain"]
    for k in kinds:
        docs.append(dict(doc_id=f"D{random.randint(10**7, 10**8 - 1)}", application_id=app_id, doc_type=k, received_date=received.isoformat(),
                         pages=random.randint(1, 14), status="Received", source=random.choice(["Branch scan", "Customer upload", "DSA upload"])))


def record_stage_history(app_id, received, final_stage):
    order = ["Login & KYC", "Credit appraisal", "Legal & technical", "Sanction", "Documentation", "Disbursed"]
    d = received
    idx = order.index(final_stage) if final_stage in order else order.index("Credit appraisal")
    for s in order[: idx + 1]:
        lo, hi = STAGE_DAYS.get(s, (0, 0))
        days = random.randint(lo, hi) if s != final_stage else None
        end = add_working_days(d, days) if days is not None else None
        stage_history.append(dict(application_id=app_id, stage=s, entered_on=d.isoformat(), exited_on=end.isoformat() if end else "", working_days=days if days is not None else ""))
        if end:
            d = end
    return d


app_seq = 104400


def make_application(c, city, age, *, loan_amount=None, prop=None, income=None, score=None, obligations=None, received=None, stage=None,
                     tenor=None, purpose=None, channel=None, co_applicant=None, hero=None, officer=None, co_owner=True, income_main=None, income_co=None):
    global app_seq
    app_seq += 1
    app_id = f"HL-2026-{app_seq}"
    self_emp = c["occupation_type"] != "Salaried"
    received = received or rnd_date(TODAY - dt.timedelta(days=120), TODAY - dt.timedelta(days=1))
    if stage is None:
        age_days = (TODAY - received).days
        if age_days < 6:
            stage = pick([("Login & KYC", 0.5), ("Credit appraisal", 0.5)])
        elif age_days < 20:
            stage = pick([("Credit appraisal", 0.4), ("Legal & technical", 0.4), ("Sanction", 0.15), ("Withdrawn", 0.05)])
        elif age_days < 40:
            stage = pick([("Legal & technical", 0.25), ("Sanction", 0.2), ("Documentation", 0.25), ("Disbursed", 0.15), ("Declined", 0.1), ("Withdrawn", 0.05)])
        else:
            stage = pick([("Documentation", 0.1), ("Disbursed", 0.7), ("Declined", 0.13), ("Withdrawn", 0.07)])
    stage_entered = record_stage_history(app_id, received, stage if stage not in ("Declined", "Withdrawn") else "Credit appraisal")
    loan_amount = loan_amount or round(random.choice([random.uniform(15, 40), random.uniform(35, 75), random.uniform(60, 160)]) * 1e5, -4)
    prop = prop or property_for(city, loan_amount / random.uniform(0.6, 0.85))
    tenor = tenor or min(360, (65 - age) * 12, random.choice([180, 240, 240, 300, 300, 360]))
    purpose = purpose or ("Purchase - under construction" if prop["construction_status"] == "Under construction" else random.choice(["Purchase - resale", "Purchase - resale", "Construction on own plot", "Balance transfer + top-up"]))
    officer = officer or next((o for o in OFFICERS if city[0] in o), random.choice(OFFICERS))
    a = dict(application_id=app_id, customer_id=c["customer_id"], co_applicant_id=co_applicant["customer_id"] if co_applicant else "", co_applicant_is_co_owner=bool(co_applicant) and co_owner,
             channel=channel or pick(CHANNELS), branch_code=c["home_branch"], received_date=received.isoformat(), loan_amount=loan_amount,
             tenor_months=tenor, purpose=purpose, property_id=prop["property_id"], applicant_age=age, declared_monthly_income=round(income or 0), declared_income_main=round(income_main if income_main is not None else (income or 0)), declared_income_co=round(income_co or 0),
             stage=stage, stage_entered_date=stage_entered.isoformat(), assigned_officer=officer, is_demo_case=bool(hero), demo_label=hero or "")
    apps.append(a)
    stamp_docs(app_id, c["occupation_type"], received)
    return a


# ---------------------------------------------------------------- hero cases
def hero_cases():
    out = {}
    pune = CITIES[0]; amd = CITIES[5]; lko = CITIES[6]; ggn = CITIES[10]

    # 1. Priya - clean salaried case, within branch powers
    c, city, age = new_customer(first="Priya", last="Raghavan", gender="F", city=pune, age=34, occupation="Salaried", employer="Kestrel Infotech Ltd", employer_category="A", pan="BQRPR4821K")
    sb = add_account(c["customer_id"], "SB", "2016-07-11", 410000)
    add_account(c["customer_id"], "FD", "2023-02-01", 600000)
    car = add_existing_loan(c["customer_id"], "Car loan", 14500, 22)
    monthly_txn(sb, 142000, 9000, 61000, 14500)
    bureau_report(c, 792, [car], 1)
    p = property_for(pune, 9200000, "Apartment", True)
    p.update(builder="Aaranya Developers", project_name="Aaranya Courtyard", rera_number="RERA-PUN-52118", address="Tower B, Flat 1104, Aaranya Courtyard, Hinjewadi Phase 2, Pune 411057", carpet_area_sqft=1085)
    a = make_application(c, city, age, loan_amount=6800000, prop=p, income=142000, received=dt.date(2026, 10, 20), stage="Credit appraisal", tenor=300,
                         purpose="Purchase - under construction", channel="Builder tie-up", hero="Clean file: recommend sanction")
    cersai[p["property_id"]] = dict(property_id=p["property_id"], search_ref=f"CS{random.randint(10**9, 10**10 - 1)}", charges=[])
    valuations.append(dict(application_id=a["application_id"], valuer="M/s Deshpande Valuers (empanelled)", valuation_date="2026-10-22", market_value=9400000, realisable_value=8460000, distress_value=7520000, remarks="Construction at 9th-floor slab; 62% complete. Rate in line with micro-market."))
    legal.append(dict(application_id=a["application_id"], advocate="Adv. S. Phadke (panel)", report_date="2026-10-22", search_years=30, title_status="Clear and marketable", encumbrance="Project land mortgaged to Northern Realty Fund; NOC for unit 1104 issued", remarks="Builder project approved (APF). Tripartite agreement required."))
    kyc[c["pan"]] = dict(pan=c["pan"], pan_status="Valid", name_on_pan="PRIYA RAGHAVAN", name_match=99, aadhaar_seeded=True, ckyc_number=f"6{random.randint(10**12, 10**13 - 1)}")
    epfo[c["uan"]] = dict(uan=c["uan"], employer="KESTREL INFOTECH LTD", establishment_id="PUPUN0012345", last_contribution_month=MONTHS12[-1], epf_wage=78000, months_continuous=58)
    aa[c["customer_id"]] = dict(consent_id=f"AA-{random.randint(10**7, 10**8 - 1)}", fip="This bank + HDFC-like FIP (simulated)", months=6, avg_monthly_credit=151200, avg_salary_credit=142300, avg_eod_balance=402000, bounces=0, emi_debits_detected=[14500])
    out["priya"] = dict(app=a, cust=c, prop=p)

    # 2. Arjun - self-employed, FOIR tipped over cap by the 7 Oct repo hike
    c, city, age = new_customer(first="Arjun", last="Mehta", gender="M", city=amd, age=41, occupation="Self-employed business", employer="Mehta Packaging", pan="AKZPM7712D")
    c["gstin"] = "24AKZPM7712D1Z5"
    ca = add_account(c["customer_id"], "CA", "2012-04-02", 640000)
    sb = add_account(c["customer_id"], "SB", "2010-09-15", 185000)
    car = add_existing_loan(c["customer_id"], "Car loan", 6150, 30)
    monthly_txn(ca, 0, 690000, 640000, 0)
    monthly_txn(sb, 0, 98000, 72000, 6150)
    bureau_report(c, 741, [car], 2)
    p = property_for(amd, 7400000, "Apartment", False)
    p.update(builder="", project_name="Shantivan Apartments (resale)", address="Flat 7B, Shantivan Apartments, Satellite Road, Ahmedabad 380015", carpet_area_sqft=1240, age_years=9)
    spouse, _, _ = new_customer(first="Kavya", last="Mehta", gender="F", city=amd, age=38, occupation="Salaried", employer="Govt. of Gujarat (Education)", employer_category="Govt")
    a = make_application(c, city, age, loan_amount=5500000, prop=p, income=98000, received=dt.date(2026, 10, 3), stage="Credit appraisal", tenor=240,
                         purpose="Purchase - resale", channel="Branch", co_applicant=spouse, co_owner=False, income_co=38200, hero="Repo hike tips FOIR over cap: deviation")
    cersai[p["property_id"]] = dict(property_id=p["property_id"], search_ref=f"CS{random.randint(10**9, 10**10 - 1)}", charges=[])
    valuations.append(dict(application_id=a["application_id"], valuer="M/s Patel & Associates (empanelled)", valuation_date="2026-10-09", market_value=7100000, realisable_value=6390000, distress_value=5680000, remarks="9-year-old RCC structure, good upkeep. Agreement value 4% above valuation."))
    legal.append(dict(application_id=a["application_id"], advocate="Adv. N. Trivedi (panel)", report_date="2026-10-12", search_years=30, title_status="Clear and marketable", encumbrance="Nil", remarks="Society NOC and share certificate verified."))
    kyc[c["pan"]] = dict(pan=c["pan"], pan_status="Valid", name_on_pan="ARJUN MEHTA", name_match=100, aadhaar_seeded=True, ckyc_number=f"6{random.randint(10**12, 10**13 - 1)}")
    gst[c["gstin"]] = dict(gstin=c["gstin"], legal_name="ARJUN MEHTA (MEHTA PACKAGING)", status="Active", registration_date="2014-07-01", turnover_12m=8160000, returns_filed_12m=12, returns_late_12m=1)
    aa[c["customer_id"]] = dict(consent_id=f"AA-{random.randint(10**7, 10**8 - 1)}", fip="This bank (CA + SB)", months=12, avg_monthly_credit=742000, avg_salary_credit=0, avg_eod_balance=612000, bounces=0, emi_debits_detected=[6150])
    epfo[spouse["uan"]] = dict(uan=spouse["uan"], employer="GOVT OF GUJARAT", establishment_id="GJAHD0099887", last_contribution_month=MONTHS12[-1], epf_wage=41000, months_continuous=110)
    kyc[spouse["pan"]] = dict(pan=spouse["pan"], pan_status="Valid", name_on_pan="KAVYA MEHTA", name_match=100, aadhaar_seeded=True, ckyc_number=f"6{random.randint(10**12, 10**13 - 1)}")
    bureau_report(spouse, 806, [], 0)
    out["arjun"] = dict(app=a, cust=c, prop=p, spouse=spouse)

    # 3. Sunita - resale house, CERSAI shows a subsisting charge of another lender
    c, city, age = new_customer(first="Sunita", last="Yadav", gender="F", city=lko, age=38, occupation="Salaried", employer="Govt. of Uttar Pradesh (Basic Education)", employer_category="Govt", pan="CHLPY3390M")
    sb = add_account(c["customer_id"], "SB", "2014-01-20", 152000)
    monthly_txn(sb, 71500, 4000, 38000, 0)
    bureau_report(c, 768, [], 0)
    husband, _, _ = new_customer(first="Rakesh", last="Yadav", gender="M", city=lko, age=41, occupation="Salaried", employer="Pinecrest Logistics Pvt Ltd", employer_category="B")
    tw = add_existing_loan(husband["customer_id"], "Two-wheeler loan", 3200, 20, lender="Eastern Home Credit Ltd")
    bureau_report(husband, 731, [tw], 1)
    p = property_for(lko, 5200000, "Independent house", False)
    p.update(address="House 214, Sector 11, Indira Nagar, Lucknow 226016", carpet_area_sqft=1450, age_years=14)
    a = make_application(c, city, age, loan_amount=3800000, prop=p, income=71500 + 46000, income_main=71500, income_co=46000, received=dt.date(2026, 10, 1), stage="Legal & technical", tenor=240,
                         purpose="Purchase - resale", channel="DSA", co_applicant=husband, hero="CERSAI shows seller's loan still charged: legal hold")
    cersai[p["property_id"]] = dict(property_id=p["property_id"], search_ref=f"CS{random.randint(10**9, 10**10 - 1)}", charges=[
        dict(security_interest_id="SI-400019887211", charge_holder="Gomti Housing Finance Ltd", borrower="Om Prakash Srivastava (current owner / seller)", type="Equitable mortgage", created_on="2019-03-14", amount_secured=2900000, status="Subsisting - satisfaction not filed")])
    valuations.append(dict(application_id=a["application_id"], valuer="M/s Awasthi Valuers (empanelled)", valuation_date="2026-10-08", market_value=5350000, realisable_value=4815000, distress_value=4280000, remarks="G+1 independent house, approved map on record."))
    legal.append(dict(application_id=a["application_id"], advocate="Adv. R. Tandon (panel)", report_date="2026-10-14", search_years=30, title_status="Clear subject to release of existing mortgage", encumbrance="EC shows mortgage by deposit of title deeds in favour of Gomti Housing Finance Ltd (2019). Seller states loan closed in 2025.", remarks="Obtain NOC, original title deeds and CERSAI satisfaction from Gomti HFL before disbursement."))
    kyc[c["pan"]] = dict(pan=c["pan"], pan_status="Valid", name_on_pan="SUNITA YADAV", name_match=100, aadhaar_seeded=True, ckyc_number=f"6{random.randint(10**12, 10**13 - 1)}")
    kyc[husband["pan"]] = dict(pan=husband["pan"], pan_status="Valid", name_on_pan="RAKESH YADAV", name_match=100, aadhaar_seeded=True, ckyc_number=f"6{random.randint(10**12, 10**13 - 1)}")
    epfo[husband["uan"]] = dict(uan=husband["uan"], employer="PINECREST LOGISTICS PVT LTD", establishment_id="UPLKO0044556", last_contribution_month=MONTHS12[-1], epf_wage=27000, months_continuous=41)
    aa[c["customer_id"]] = dict(consent_id=f"AA-{random.randint(10**7, 10**8 - 1)}", fip="This bank (SB)", months=6, avg_monthly_credit=75400, avg_salary_credit=71500, avg_eod_balance=148000, bounces=0, emi_debits_detected=[])
    out["sunita"] = dict(app=a, cust=c, prop=p, co=husband)

    # 4. Vikram - payslip does not match bank credits, Form 16 or EPFO: refer to RCU
    c, city, age = new_customer(first="Vikram", last="Sethi", gender="M", city=ggn, age=29, occupation="Salaried", employer="Meghdoot Retail Pvt Ltd", employer_category="B", pan="DNSPS6604R")
    sb = add_account(c["customer_id"], "SB", "2021-08-09", 64000)
    pl = add_existing_loan(c["customer_id"], "Personal loan", 11800, 14)
    monthly_txn(sb, 88400, 3000, 58000, 11800)
    bureau_report(c, 724, [pl], 4)
    p = property_for(ggn, 8900000, "Apartment", False)
    p.update(builder="", project_name="Silver Oaks (resale)", address="Flat 603, Silver Oaks, Sector 49, Gurugram 122018", carpet_area_sqft=960, age_years=6)
    a = make_application(c, city, age, loan_amount=6900000, prop=p, income=135000, received=dt.date(2026, 10, 15), stage="Credit appraisal", tenor=300,
                         purpose="Purchase - resale", channel="DSA", hero="Payslip doesn't match bank and Form 16: refer to RCU")
    cersai[p["property_id"]] = dict(property_id=p["property_id"], search_ref=f"CS{random.randint(10**9, 10**10 - 1)}", charges=[])
    valuations.append(dict(application_id=a["application_id"], valuer="M/s Arora Techno Valuers (empanelled)", valuation_date="2026-10-19", market_value=8750000, realisable_value=7875000, distress_value=7000000, remarks="Ready unit, OC available."))
    legal.append(dict(application_id=a["application_id"], advocate="Adv. M. Bedi (panel)", report_date="2026-10-21", search_years=30, title_status="Clear and marketable", encumbrance="Nil", remarks="Conveyance deed registered 2021."))
    kyc[c["pan"]] = dict(pan=c["pan"], pan_status="Valid", name_on_pan="VIKRAM SETHI", name_match=100, aadhaar_seeded=True, ckyc_number=f"6{random.randint(10**12, 10**13 - 1)}")
    epfo[c["uan"]] = dict(uan=c["uan"], employer="MEGHDOOT RETAIL PVT LTD", establishment_id="HRGGN0077123", last_contribution_month=MONTHS12[-1], epf_wage=46500, months_continuous=27)
    aa[c["customer_id"]] = dict(consent_id=f"AA-{random.randint(10**7, 10**8 - 1)}", fip="This bank (SB)", months=6, avg_monthly_credit=91600, avg_salary_credit=88400, avg_eod_balance=61000, bounces=0, emi_debits_detected=[11800])
    out["vikram"] = dict(app=a, cust=c, prop=p)
    return out


HEROES = hero_cases()

# ---------------------------------------------------------------- the rest of the book
for _ in range(N_APPS - len(HEROES)):
    c, city, age = new_customer()
    self_emp = c["occupation_type"] != "Salaried"
    income = random.lognormvariate(math.log(85000 if not self_emp else 110000), 0.45)
    income = max(28000, min(income, 650000))
    score = int(random.gauss(752, 42))
    if random.random() < 0.04:
        score = -1  # new to credit
    score = max(-1, min(score, 880))
    ob = []
    for prod, prob in [("Car loan", 0.28), ("Personal loan", 0.2), ("Two-wheeler loan", 0.08), ("Education loan", 0.05)] + ([("Business loan", 0.3)] if self_emp else []):
        if random.random() < prob:
            lender = "This bank" if random.random() < 0.45 else random.choice(OTHER_LENDERS + ["Other bank"])
            dpd = None
            if score != -1 and score < 690 and random.random() < 0.5:
                dpd = [0] * 12
                dpd[random.randint(4, 11)] = random.choice([15, 30, 45])
            ob.append(add_existing_loan(c["customer_id"], prod, income * random.uniform(0.04, 0.14), random.randint(3, 40), dpd, lender))
    acct_kind = "CA" if self_emp else "SB"
    acc = add_account(c["customer_id"], acct_kind, c["customer_since"], income * random.uniform(0.8, 4))
    monthly_txn(acc, 0 if self_emp else income, income * (5 if self_emp else 0.1), income * (4.4 if self_emp else 0.55), sum(l["emi"] for l in ob), bounces=1 if random.random() < 0.05 else 0)
    max_dpd = max([max(r["dpd"] for r in repayments if r["loan_id"] == l["loan_id"]) for l in ob if l["lender"] == "This bank"] + [0])
    bureau_report(c, score, ob, random.choice([0, 0, 1, 1, 2, 3, 5]), max_dpd, writeoff=(score != -1 and score < 650 and random.random() < 0.3))
    # size the loan off affordability with noise, so some files breach
    r = rate_for(REPO_OLD, score, self_emp)
    tenor = min(360, (65 - age) * 12, random.choice([180, 240, 240, 300, 300, 360]))
    received = rnd_date(TODAY - dt.timedelta(days=120), TODAY - dt.timedelta(days=1))
    target_foir = random.uniform(0.30, 0.53) if random.random() < 0.85 else random.uniform(0.53, 0.66)
    if dt.date(2026, 9, 15) <= received < REPO_CHANGE and random.random() < 0.45:
        inc_cap = 0.5 if income <= 50000 else 0.55 if income <= 100000 else 0.6
        target_foir = inc_cap - random.uniform(0.002, 0.009)  # borderline at the old rate
    emi_room = max(5000, income * target_foir - sum(l["emi"] for l in ob))
    i = r / 1200
    loan = emi_room * ((1 + i) ** tenor - 1) / (i * (1 + i) ** tenor)
    loan = round(max(800000, min(loan, 25000000)), -4)
    cap = 0.9 if loan <= 3000000 else 0.8 if loan <= 7500000 else 0.75
    ltv = random.uniform(0.55, cap - 0.04) if random.random() < 0.93 else random.uniform(cap - 0.02, cap + 0.04)
    prop = property_for(city, loan / ltv)
    co = None
    if random.random() < 0.3:
        co, _, _ = new_customer(city=city, last=c["full_name"].split()[-1], occupation="Salaried")
    co_inc = round(income * random.uniform(0.3, 0.8)) if co else 0
    a = make_application(c, city, age, loan_amount=loan, prop=prop, income=income + co_inc, tenor=tenor, received=received, co_applicant=co, income_main=income, income_co=co_inc, co_owner=random.random() < 0.85)
    for k in ("pan",):
        kyc[c["pan"]] = dict(pan=c["pan"], pan_status="Valid" if random.random() > 0.01 else "Invalid - not found", name_on_pan=c["full_name"].upper(),
                             name_match=random.choice([100, 100, 98, 96, 92, 81]), aadhaar_seeded=random.random() > 0.03, ckyc_number=f"6{random.randint(10**12, 10**13 - 1)}")
    charges = []
    if random.random() < 0.035:
        charges.append(dict(security_interest_id=f"SI-4000{random.randint(10**7, 10**8 - 1)}", charge_holder=random.choice(OTHER_LENDERS), borrower="Current owner / seller",
                            type="Equitable mortgage", created_on=rnd_date(dt.date(2015, 1, 1), dt.date(2024, 1, 1)).isoformat(), amount_secured=round(loan * 0.6, -4), status="Subsisting - satisfaction not filed"))
    cersai[prop["property_id"]] = dict(property_id=prop["property_id"], search_ref=f"CS{random.randint(10**9, 10**10 - 1)}", charges=charges)
    if a["stage"] not in ("Login & KYC", "Credit appraisal"):
        mv = prop["agreement_value"] * (random.uniform(0.97, 1.08) if random.random() < 0.85 else random.uniform(0.86, 0.97))
        valuations.append(dict(application_id=a["application_id"], valuer="Empanelled valuer", valuation_date=a["stage_entered_date"], market_value=round(mv, -4),
                               realisable_value=round(mv * 0.9, -4), distress_value=round(mv * 0.8, -4), remarks=""))
        legal.append(dict(application_id=a["application_id"], advocate="Panel advocate", report_date=a["stage_entered_date"], search_years=30,
                          title_status="Clear and marketable" if not charges else "Clear subject to release of existing mortgage", encumbrance="Nil" if not charges else "Existing mortgage on record", remarks=""))
    if c["uan"]:
        epfo[c["uan"]] = dict(uan=c["uan"], employer=c["employer_name"].upper(), establishment_id=f"XX{random.randint(10**8, 10**9 - 1)}", last_contribution_month=MONTHS12[-1],
                              epf_wage=round(income * random.uniform(0.45, 0.6)), months_continuous=random.randint(6, 140))
    if c["gstin"]:
        gst[c["gstin"]] = dict(gstin=c["gstin"], legal_name=c["full_name"].upper(), status="Active", registration_date=c["customer_since"], turnover_12m=round(income * 12 * random.uniform(5, 9), -4),
                               returns_filed_12m=random.choice([12, 12, 12, 11, 10]), returns_late_12m=random.choice([0, 0, 1, 2, 4]))
    aa[c["customer_id"]] = dict(consent_id=f"AA-{random.randint(10**7, 10**8 - 1)}", fip="This bank", months=6, avg_monthly_credit=round(income * (5.5 if self_emp else 1.05)),
                                avg_salary_credit=0 if self_emp else round(income * random.uniform(0.97, 1.01)), avg_eod_balance=acc["avg_monthly_balance_6m"], bounces=0, emi_debits_detected=[l["emi"] for l in ob])

# ---------------------------------------------------------------- officer decision history (feedback loop)
REASONS_OVERRIDE = [
    ("Accepted co-applicant income the agent had excluded (co-owner added at sanction)", "Sanction", "Refer"),
    ("Valuation variance explained by recent comparable sales", "Sanction", "Refer"),
    ("Long relationship and salary account with bank for 10+ years", "Sanction", "Refer"),
    ("Bureau enquiries were for the same home loan across lenders", "Sanction", "Refer"),
    ("Officer more conservative: builder project progress slow", "Refer", "Sanction"),
    ("Employer on internal watch list", "Refer", "Sanction"),
]
past = [a for a in apps if a["stage"] in ("Documentation", "Disbursed", "Declined") and not a["is_demo_case"]]
for a in past:
    agent_rec = "Decline" if a["stage"] == "Declined" else random.choice(["Sanction"] * 7 + ["Sanction with conditions"] * 3 + ["Refer"])
    officer = agent_rec
    reason = ""
    if random.random() < 0.11:
        reason, officer, agent_rec = random.choice(REASONS_OVERRIDE)
    decisions.append(dict(application_id=a["application_id"], decided_on=a["stage_entered_date"], agent_recommendation=agent_rec, officer_decision=officer,
                          override=officer != agent_rec, override_reason=reason, decided_by=a["assigned_officer"], source="Historical (synthetic)"))

# ---------------------------------------------------------------- write
def write_csv(name, rows):
    if not rows:
        return
    keys = list(rows[0].keys())
    with open(os.path.join(OUT, name + ".csv"), "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=keys)
        w.writeheader()
        for r in rows:
            w.writerow({k: (json.dumps(v) if isinstance(v, (list, dict)) else int(v) if isinstance(v, bool) else v) for k, v in r.items()})


write_csv("core_customers", customers)
write_csv("core_accounts", accounts)
write_csv("core_loans", loans)
write_csv("core_repayments", repayments)
write_csv("core_txn_monthly", txns)
write_csv("los_applications", apps)
write_csv("los_stage_history", stage_history)
write_csv("los_documents", docs)
write_csv("properties", properties)
write_csv("valuation_reports", valuations)
write_csv("legal_reports", legal)
write_csv("officer_decisions_history", decisions)
# landed external responses (bronze copies of what the APIs returned at login time)
write_csv("ext_bureau", [dict(pan=k, pulled_on=v["report_date"], score=v["score"], enquiries_last_90d=v["enquiries_last_90d"], max_dpd_last_12m=v["max_dpd_last_12m"],
                               written_off_or_settled_36m=v["written_off_or_settled_36m"], tradelines=len(v["accounts"]), total_emi=sum(x["emi"] for x in v["accounts"]), payload=v) for k, v in bureau.items()])
write_csv("ext_cersai", [dict(property_id=k, searched_on=TODAY.isoformat(), subsisting_charges=len(v["charges"]), payload=v) for k, v in cersai.items()])
write_csv("ext_kyc", list(kyc.values()))
write_csv("ext_aa", [dict(customer_id=k, **{kk: vv for kk, vv in v.items() if kk != "emi_debits_detected"}, emi_debits_detected=sum(v["emi_debits_detected"])) for k, v in aa.items()])
write_csv("ext_epfo", list(epfo.values()))
write_csv("ext_gst", list(gst.values()))
write_csv("rate_card", [dict(effective_from="2025-12-05", effective_to=REPO_CHANGE.isoformat(), repo_rate=REPO_OLD, eblr_spread=2.70, note="EBLR = repo + 2.70%"),
                        dict(effective_from=REPO_CHANGE.isoformat(), effective_to="2099-12-31", repo_rate=REPO_NEW, eblr_spread=2.70, note="MPC 7 Oct 2026: repo +25 bps")])

for name, obj in [("bureau", bureau), ("cersai", cersai), ("kyc", kyc), ("aa", aa), ("epfo", epfo), ("gst", gst)]:
    with open(os.path.join(WORLD, name + ".json"), "w") as f:
        json.dump(obj, f, indent=1)

with open(os.path.join(ROOT, "data", "out", "heroes.json"), "w") as f:
    json.dump({k: {kk: vv for kk, vv in v.items()} for k, v in HEROES.items()}, f, indent=1, default=str)

print("customers", len(customers), "apps", len(apps), "accounts", len(accounts), "loans", len(loans), "repayments", len(repayments), "txns", len(txns), "docs", len(docs), "decisions", len(decisions))
for k, v in HEROES.items():
    print(k, v["app"]["application_id"], v["cust"]["customer_id"])
