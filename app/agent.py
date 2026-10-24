"""The Credit Case Agent.

One agent with four skills, run as a fixed workflow so every file gets the same checks in the same
order (consistency is the point), with a parallel fan-out for the external checks:

  1 Open the file        read the application and the customer's history from the lakehouse
  2 Read documents       Gemini reads each PDF and returns fields; the agent cross-checks sources
  3 Verify externally    KYC, bureau, CERSAI, Account Aggregator, EPFO / GST in parallel
  4 Apply policy         deterministic rules, each citing a policy clause; arithmetic is code, not AI
  5 Recommend & route    decision, deviations, conditions, sanctioning authority
  6 Draft the note       Gemini writes the note for sanction from the verified facts only
  7 Hand off             the file goes to a named human; nothing is sanctioned or declined by the agent

Every event is streamed to the UI and written to lending_gold.agent_audit.
"""
import concurrent.futures as cf
import datetime as dt
import json, os, re, threading, time, uuid

import gcp, mocks, store
from policy_pack import PARAMS, CLAUSE_BY_ID, cap_for, rate_for, emi

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HERO_DOCS = json.load(open(os.path.join(ROOT, "data", "out", "hero_docs.json")))
AI_ENABLED = bool(gcp.PROJECT) and os.environ.get("USE_GEMINI", "1") == "1"
RUNS = {}

STEPS = [
    ("open", "Open the file", "Lakehouse (BigQuery)"),
    ("documents", "Read and cross-check documents", "Gemini on Vertex AI"),
    ("verify", "Verify with external sources", "Mock CIBIL, CERSAI, PAN/CKYC, AA, EPFO, GST"),
    ("policy", "Apply credit policy", "Policy pack v4.2 + RBI rules"),
    ("recommend", "Recommend and route", "Delegation of powers (HLP-9.1)"),
    ("note", "Draft the note for sanction", "Gemini on Vertex AI"),
    ("handoff", "Hand off to the credit officer", "Human in the loop"),
]


def now():
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def lakh(x):
    return f"Rs {x / 1e5:,.2f} lakh"


class Run:
    def __init__(self, app_id):
        self.run_id = "R" + uuid.uuid4().hex[:10]
        self.app_id = app_id
        self.events = []
        self.done = False
        self.result = None
        self.lock = threading.Lock()
        self.audit = []

    def emit(self, step, etype, **data):
        ev = dict(i=len(self.events), ts=now(), step=step, type=etype, **data)
        with self.lock:
            self.events.append(ev)
        self.audit.append(dict(run_id=self.run_id, application_id=self.app_id, ts=ev["ts"], step=step, event_type=etype,
                               detail=json.dumps({k: v for k, v in data.items() if k not in ("sql",)}, default=str)[:9000]))

    def flush_audit(self):
        rows, self.audit = self.audit, []
        store.insert("lending_gold", "agent_audit", rows)


def start(app_id):
    run = Run(app_id)
    RUNS[run.run_id] = run
    threading.Thread(target=_execute, args=(run,), daemon=True).start()
    return run


# ------------------------------------------------------------------------------------------ helpers
def _num(v):
    if isinstance(v, (int, float)):
        return v
    if v is None:
        return None
    s = re.sub(r"[^\d.\-]", "", str(v))
    try:
        return float(s) if "." in s else int(s)
    except ValueError:
        return v


def _q(run, step, name, purpose, **params):
    rows, meta = store.query(name, **params)
    run.emit(step, "tool", tool="read_database", source="Lakehouse", target=name, purpose=purpose, sql=meta["sql"],
             engine=meta["engine"], ms=meta["ms"], bytes_processed=meta.get("bytes_processed"), rows=len(rows))
    return rows


def read_document(doc):
    """Gemini reads the PDF and returns the fields; offline the pre-extracted values are used."""
    keys = list(doc["fields"].keys())
    if AI_ENABLED:
        try:
            pdf = open(os.path.join(ROOT, "web", doc["file"].lstrip("/")), "rb").read()
            t0 = time.time()
            prompt = (f"You are reading a '{doc['doc_type']}' submitted with an Indian home loan application. "
                      f"Return a JSON object with exactly these keys: {keys}. Use numbers (no commas or currency symbols) for amounts. "
                      "If a value is not present in the document, use null. Do not infer values that are not printed.")
            text, model = gcp.gemini([("application/pdf", pdf), prompt], json_mode=True, timeout=40)
            fields = json.loads(text)
            if isinstance(fields, list):
                fields = fields[0]
            fields = {k: _num(fields.get(k)) if isinstance(doc["fields"].get(k), (int, float)) else fields.get(k) for k in keys}
            return fields, dict(mode="gemini", model=model, ms=int((time.time() - t0) * 1000))
        except Exception as e:
            return dict(doc["fields"]), dict(mode="fallback", error=str(e)[:200])
    return dict(doc["fields"]), dict(mode="offline")


def max_loan(emi_room, rate, months):
    if emi_room <= 0:
        return 0
    i = rate / 1200
    return emi_room * ((1 + i) ** months - 1) / (i * (1 + i) ** months)


# ------------------------------------------------------------------------------------------ the run
def _execute(run):
    try:
        _run(run)
    except Exception as e:
        import traceback
        traceback.print_exc()
        run.emit("handoff", "error", message=f"The agent stopped: {e}. The file is unchanged and stays with the officer.")
    finally:
        run.done = True
        try:
            run.flush_audit()
        except Exception as e:
            print("audit flush failed", e)


def _run(run):
    app_id = run.app_id
    # ---------------------------------------------------------------- 1 open the file
    s = "open"
    run.emit(s, "step_start", title=STEPS[0][1], uses=STEPS[0][2])
    app = _q(run, s, "application", "Application, applicant and KYC identifiers from the loan origination system", app_id=app_id)[0]
    prop = _q(run, s, "property", "Property, valuation and legal reports", app_id=app_id)[0]
    rel = _q(run, s, "relationship", "Relationship with the bank from core banking", customer_id=app["customer_id"])[0]
    rep = _q(run, s, "repayment", "Repayment track of loans with the bank (12 months)", customer_id=app["customer_id"])
    bank = (_q(run, s, "bank_income", "Salary and credits seen in the bank's own accounts", customer_id=app["customer_id"]) or [{}])[0]
    feat = _q(run, s, "features", "Batch screening row from the gold layer", app_id=app_id)[0]
    co = None
    if app.get("co_applicant_id"):
        co = _q(run, s, "co_applicant", "Co-applicant profile", customer_id=app["co_applicant_id"])[0]
    self_emp = app["occupation_type"] != "Salaried"
    run.emit(s, "finding", status="info", text=f"{app['full_name']}, {app['occupation_type'].lower()}, {app['city']}. Asks {lakh(app['loan_amount'])} over {app['tenor_months'] // 12} years for {app['purpose'].lower()}."
             + (f" Customer since {str(rel['banking_since'])[:4]} with {rel['accounts']} account(s)." if rel.get("banking_since") else ""))
    run.emit(s, "step_end")
    run.flush_audit()

    # ---------------------------------------------------------------- 2 documents
    s = "documents"
    run.emit(s, "step_start", title=STEPS[1][1], uses=STEPS[1][2])
    docs = HERO_DOCS.get(app_id, [])
    read = {}
    if docs:
        with cf.ThreadPoolExecutor(max_workers=5) as ex:
            futs = {ex.submit(read_document, d): d for d in docs}
            for f in cf.as_completed(futs):
                d = futs[f]
                fields, how = f.result()
                read[d["doc_key"]] = fields
                run.emit(s, "document", doc_type=d["doc_type"], file=d["file"], fields=fields, how=how)
    else:
        idx = _q(run, s, "documents_index", "Documents received for this file", app_id=app_id)
        run.emit(s, "finding", status="info", text=f"{len(idx)} documents are indexed for this file. Only the four demo files carry full document images; for this one the agent uses the values captured at login.")
    doc_findings = []
    if docs and not self_emp:
        slip = read.get("salary_slip", {})
        payslip = _num(slip.get("net_monthly_avg_3m"))
        bank_sal = _num(read.get("bank_statement", {}).get("avg_monthly_salary_credit")) or bank.get("salary_credit_avg_3m")
        f16 = _num(read.get("form16", {}).get("net_after_tax_monthly_equiv"))
        if payslip and bank_sal:
            var = round(100 * (payslip - bank_sal) / payslip, 1)
            st = "fail" if abs(var) > PARAMS["income_variance_pct"] else "pass"
            txt = (f"Salary slip shows net pay of Rs {payslip:,.0f} a month; salary credited to the bank averages Rs {bank_sal:,.0f}" + (f"; Form 16 implies Rs {f16:,.0f}" if f16 else "") + f". Gap {var}%.")
            doc_findings.append(dict(status=st, text=txt + (" Sources disagree beyond the 15% tolerance." if st == "fail" else " Sources agree."), clause="HLP-4.2"))
    if docs and self_emp:
        itr = read.get("itr", {})
        gstd = read.get("gst", {})
        t_itr, t_gst = _num(itr.get("turnover_fy2025_26")), _num(gstd.get("turnover_12m"))
        if t_itr and t_gst:
            var = round(100 * abs(t_gst - t_itr) / t_itr, 1)
            doc_findings.append(dict(status="pass" if var <= 20 else "flag", clause="HLP-4.3",
                                     text=f"ITR turnover Rs {t_itr / 1e5:,.1f} lakh vs GST turnover Rs {t_gst / 1e5:,.1f} lakh: {var}% apart (tolerance 20%)."))
    if docs:
        agr = None
        for k in ("allotment", "sale_agreement", "sale_deed_draft"):
            if k in read:
                agr = _num(read[k].get("agreement_value"))
        if agr and abs(agr - prop["agreement_value"]) > 1000:
            doc_findings.append(dict(status="flag", clause="HLP-5.1", text=f"Agreement value in the document (Rs {agr:,.0f}) differs from the loan system (Rs {prop['agreement_value']:,.0f})."))
        elif agr:
            doc_findings.append(dict(status="pass", clause="HLP-5.1", text=f"Agreement value Rs {agr / 1e5:,.2f} lakh matches the loan system."))
        if "encumbrance" in read and "sale_deed_draft" in read:
            ec = read["encumbrance"]
            decl = read["sale_deed_draft"].get("seller_declaration", "")
            if "No release" in str(ec.get("release_recorded", "")):
                doc_findings.append(dict(status="fail", clause="HLP-6.1", text=f"Seller declares the property free of encumbrances (\"{decl[:90]}...\"), but the encumbrance certificate records a 2019 mortgage with no release."))
        if "sale_agreement" in read and co and not app.get("co_applicant_is_co_owner"):
            doc_findings.append(dict(status="info", clause="HLP-4.4", text=f"Sale agreement names {app['full_name']} as sole purchaser; co-applicant {co['full_name']} is not a co-owner."))
    for f in doc_findings:
        run.emit(s, "finding", **f)
    run.emit(s, "step_end")
    run.flush_audit()

    # ---------------------------------------------------------------- 3 verify externally (parallel)
    s = "verify"
    run.emit(s, "step_start", title=STEPS[2][1], uses=STEPS[2][2])
    calls = [("kyc", app["pan"], "Applicant"), ("bureau", app["pan"], "Applicant"), ("cersai", app["property_id"], "Property"), ("aa", app["customer_id"], "Applicant")]
    calls.append(("gst", app["gstin"], "Business") if self_emp and app.get("gstin") else ("epfo", str(app.get("uan") or ""), "Applicant"))
    if co:
        calls += [("kyc", co["pan"], "Co-applicant"), ("bureau", co["pan"], "Co-applicant")]
    ext = {}
    api_log = []
    with cf.ThreadPoolExecutor(max_workers=8) as ex:
        futs = {ex.submit(mocks.call, svc, key): (svc, key, who) for svc, key, who in calls}
        for f in cf.as_completed(futs):
            svc, key, who = futs[f]
            r = f.result()
            ext[(svc, who)] = r["response"]
            run.emit(s, "tool", tool=f"{svc}_api", source=r["name"], target=r["provider"], who=who, ms=r["latency_ms"], cost_inr=r["cost_inr"],
                     summary=_summarise(svc, r["response"]), response=r["response"])
            api_log.append(dict(run_id=run.run_id, ts=now(), service=svc, request_key=str(key), latency_ms=r["latency_ms"], cost_inr=r["cost_inr"], response=json.dumps(r["response"])[:9000]))
    store.insert("lending_raw", "ext_api_log", api_log)
    total_cost = sum(c["cost_inr"] for c in api_log)
    run.emit(s, "finding", status="info", text=f"{len(api_log)} calls ran in parallel; slowest {max(c['latency_ms'] for c in api_log) / 1000:.1f}s; cost Rs {total_cost:,.0f} (illustrative). Responses landed in lending_raw.ext_api_log.")
    run.emit(s, "step_end")
    run.flush_audit()

    # ---------------------------------------------------------------- 4 apply policy
    s = "policy"
    run.emit(s, "step_start", title=STEPS[3][1], uses=STEPS[3][2])
    checks = []

    def check(cid, label, value, threshold, status, clause, evidence, detail=""):
        c = dict(id=cid, label=label, value=value, threshold=threshold, status=status, clause=clause, clause_title=CLAUSE_BY_ID[clause]["title"], evidence=evidence, detail=detail)
        checks.append(c)
        run.emit(s, "check", **c)

    kyc = ext.get(("kyc", "Applicant"), {})
    ok_kyc = kyc.get("pan_status") == "Valid" and (kyc.get("name_match") or 0) >= 90
    check("kyc", "PAN and identity", f"{kyc.get('pan_status', 'No record')}, name match {kyc.get('name_match', '-')}%", "Valid PAN, name match 90%+", "pass" if ok_kyc else "fail", "RBI-KYC-2016", ["PAN/CKYC API"],
          f"CKYC {kyc.get('ckyc_number', 'not found')}")

    age_mat = app["applicant_age"] + app["tenor_months"] / 12
    max_age = PARAMS["max_age_at_maturity_self_employed"] if self_emp else PARAMS["max_age_at_maturity_salaried"]
    check("age", "Age at loan maturity", f"{age_mat:.0f} years", f"{max_age} or less", "pass" if age_mat <= max_age else "fail", "HLP-2.1", ["Loan system"])

    rep_b = ext.get(("bureau", "Applicant"), {}).get("report", {})
    score = rep_b.get("score")
    if score is None or score < 0:
        check("score", "Bureau score", "No score (new to credit)", "700+", "flag", "HLP-3.1", ["CIBIL"])
    else:
        st = "pass" if score >= PARAMS["score_floor"] else "flag" if score >= PARAMS["score_deviation_floor"] else "fail"
        check("score", "Bureau score", str(score), f"{PARAMS['score_floor']}+ (650-699 is a deviation)", st, "HLP-3.1", ["CIBIL"])
    dpd_bank = max([r["max_dpd_12m"] or 0 for r in rep] + [0])
    dpd = max(rep_b.get("max_dpd_last_12m", 0) or 0, dpd_bank)
    check("dpd", "Repayment track, last 12 months", f"Max {dpd} days past due", "30 days or less; no write-off in 36 months",
          "pass" if dpd <= PARAMS["max_dpd_12m"] and not rep_b.get("written_off_or_settled_36m") else "fail", "HLP-3.2", ["CIBIL", "Core banking"])
    enq = rep_b.get("enquiries_last_90d", 0)
    check("enquiries", "Credit enquiries, last 90 days", str(enq), f"{PARAMS['max_enquiries_90d']} or fewer", "pass" if enq <= PARAMS["max_enquiries_90d"] else "flag", "HLP-3.4", ["CIBIL"])

    aa = ext.get(("aa", "Applicant"), {})
    income_variance = None
    if self_emp:
        itr = read.get("itr", {})
        income_main = _num(itr.get("assessed_monthly_income")) or app["declared_income_main"]
        inc_src = "ITR, 2-year average cash income" if itr else "Declared income (no ITR image in this file)"
        turnover = _num(itr.get("turnover_fy2025_26"))
        if turnover and aa.get("avg_monthly_credit"):
            bank_turn = aa["avg_monthly_credit"] * 12
            var = round(100 * abs(bank_turn - turnover) / turnover, 1)
            check("turnover", "Banking turnover vs ITR", f"Rs {bank_turn / 1e5:,.1f} lakh vs Rs {turnover / 1e5:,.1f} lakh ({var}% apart)", "Within 20%",
                  "pass" if var <= 20 else "flag", "HLP-4.3", ["Account Aggregator", "ITR (Gemini read)"])
    else:
        bank_sal = aa.get("avg_salary_credit") or bank.get("salary_credit_avg_3m") or app["declared_income_main"]
        income_main = bank_sal
        inc_src = "Salary credits via Account Aggregator, 6-month average"
        payslip = _num(read.get("salary_slip", {}).get("net_monthly_avg_3m")) or app["declared_income_main"]
        if payslip:
            income_variance = round(100 * (payslip - bank_sal) / payslip, 1)
            ep = ext.get(("epfo", "Applicant"), {})
            epf_txt = f"; EPFO shows {ep.get('employer', '').title()} contributing for {ep.get('months_continuous')} months" if ep.get("status") == "OK" else ""
            check("income_match", "Declared vs verified salary", f"Payslip Rs {payslip:,.0f} vs bank Rs {bank_sal:,.0f} ({income_variance}%)", "Within 15%",
                  "pass" if abs(income_variance) <= PARAMS["income_variance_pct"] else "fail", "HLP-4.2", ["Salary slip (Gemini read)", "Account Aggregator", "EPFO"], epf_txt.lstrip("; "))

    co_income = 0
    co_note = ""
    if co:
        co_doc = read.get("spouse_salary") or read.get("co_salary_slip") or {}
        co_inc_val = _num(co_doc.get("net_monthly") or co_doc.get("net_monthly_avg_3m")) or app["declared_income_co"]
        if app.get("co_applicant_is_co_owner"):
            co_income = co_inc_val
            co_note = f"Includes co-applicant {co['full_name']} (co-owner): Rs {co_inc_val:,.0f}."
        else:
            co_note = f"Co-applicant {co['full_name']}'s income Rs {co_inc_val:,.0f} excluded: not a co-owner of the property."
    income = income_main + co_income

    obligations = sum(a.get("emi", 0) for a in rep_b.get("accounts", []))
    co_rep = ext.get(("bureau", "Co-applicant"), {}).get("report", {}) if co else {}
    if co and app.get("co_applicant_is_co_owner"):
        obligations += sum(a.get("emi", 0) for a in co_rep.get("accounts", []))

    rate = rate_for(score, self_emp)
    emi_now = emi(app["loan_amount"], rate, app["tenor_months"])
    cap = cap_for(PARAMS["foir_cap"], income)
    foir = 100 * (emi_now + obligations) / income
    received = str(app["received_date"])[:10]
    repo_login = 5.25 if received < "2026-10-07" else PARAMS["repo_rate"]
    rate_login = rate_for(score, self_emp, dict(PARAMS, repo_rate=repo_login))
    foir_login = 100 * (emi(app["loan_amount"], rate_login, app["tenor_months"]) + obligations) / income
    check("income", "Income assessed", f"Rs {income:,.0f} a month", inc_src, "info", "HLP-4.4" if co else ("HLP-4.3" if self_emp else "HLP-4.2"),
          ["Account Aggregator" if not self_emp else "ITR (Gemini read)"] + (["Co-applicant docs"] if co else []), co_note)
    check("rate", "Rate offered", f"{rate:.2f}% floating, EMI Rs {emi_now:,.0f}", f"Repo {PARAMS['repo_rate']:.2f}% + 2.70% + risk premium", "info", "HLP-10.1", ["Rate card", "CIBIL"],
          "Linked to the RBI repo rate (external benchmark).")
    foir_detail = f"EMI Rs {emi_now:,.0f} + existing EMIs Rs {obligations:,.0f} on income Rs {income:,.0f}."
    if abs(foir - foir_login) >= 0.05 and repo_login != PARAMS["repo_rate"]:
        foir_detail += f" At login (repo {repo_login:.2f}%) FOIR was {foir_login:.1f}%; the 7 Oct repo hike raised it."
    check("foir", "FOIR (EMIs / income)", f"{foir:.1f}%", f"{cap:.0f}% or less", "pass" if foir <= cap else ("flag" if foir <= cap + 10 else "fail"), "HLP-4.1",
          ["CIBIL", "Account Aggregator" if not self_emp else "ITR", "Rate card"], foir_detail)

    mv = prop.get("market_value")
    sec = min(prop["agreement_value"], mv) if mv else prop["agreement_value"]
    ltv = 100 * app["loan_amount"] / sec
    ltv_cap = cap_for(PARAMS["ltv_cap"], app["loan_amount"])
    check("ltv", "Loan-to-value", f"{ltv:.1f}% of Rs {sec / 1e5:,.2f} lakh", f"{ltv_cap:.0f}% or less (RBI cap)", "pass" if ltv <= ltv_cap else "flag", "RBI-LTV",
          ["Valuation report", "Sale agreement"], "Security value is the lower of agreement value and the valuer's market value.")
    if mv:
        gap = round(100 * (prop["agreement_value"] - mv) / mv, 1)
        check("valuation", "Agreement vs valuation", f"{gap:+.1f}%", "Agreement no more than 15% above valuation", "pass" if gap <= PARAMS["valuation_variance_pct"] else "flag", "HLP-5.3", ["Valuation report"],
              f"{prop.get('valuer', 'Valuer')}: market value Rs {mv / 1e5:,.2f} lakh.")
    cer = ext.get(("cersai", "Property"), {})
    charges = cer.get("subsisting_charges", [])
    if charges:
        c0 = charges[0]
        check("cersai", "CERSAI search", f"{len(charges)} subsisting charge", "No charge of another lender", "fail", "SARFAESI-CERSAI", ["CERSAI"],
              f"{c0['charge_holder']}, {c0['type'].lower()} created {c0['created_on']} for Rs {c0['amount_secured'] / 1e5:,.1f} lakh; status: {c0['status'].lower()}.")
    else:
        check("cersai", "CERSAI search", "No subsisting charge", "No charge of another lender", "pass", "SARFAESI-CERSAI", ["CERSAI"], f"Search ref {cer.get('search_ref', '-')}")
    if prop.get("title_status"):
        clear = prop["title_status"] == "Clear and marketable"
        check("title", "Legal title (30-year search)", prop["title_status"], "Clear and marketable", "pass" if clear else "flag", "HLP-6.1", ["Panel advocate report"],
              f"{prop.get('advocate', '')}: {prop.get('legal_remarks', '')}".strip(": "))
    if prop.get("construction_status") == "Under construction":
        check("rera", "Under-construction project", f"RERA {prop.get('rera_number')}, {prop.get('builder')}", "RERA registered, bank-approved project", "pass" if prop.get("rera_number") else "fail", "HLP-6.4", ["Loan system", "Allotment letter"])
    run.emit(s, "step_end")
    run.flush_audit()

    # ---------------------------------------------------------------- 5 recommend and route
    s = "recommend"
    run.emit(s, "step_start", title=STEPS[4][1], uses=STEPS[4][2])
    by = {c["id"]: c for c in checks}
    deviations, holds, declines, mitigants, options = [], [], [], [], []
    if by.get("score", {}).get("status") == "fail" or by["dpd"]["status"] == "fail" or by["age"]["status"] == "fail" or by["kyc"]["status"] == "fail":
        declines += [c for c in checks if c["status"] == "fail" and c["id"] in ("score", "dpd", "age", "kyc")]
    if by.get("income_match", {}).get("status") == "fail":
        holds.append(dict(kind="RCU", text="Salary on the payslip is not supported by bank credits, Form 16 or EPFO. Refer to the Risk Containment Unit for verification. This is a check, not a finding of fraud.", clause="HLP-7.2"))
    if by["cersai"]["status"] == "fail" or any(f["status"] == "fail" and f["clause"] == "HLP-6.1" for f in doc_findings):
        holds.append(dict(kind="Legal", text="A mortgage in favour of another lender is still on record and contradicts the seller's declaration. Raise a legal query: obtain the lender's NOC, original title deeds and CERSAI satisfaction, and have the panel advocate re-vet the title.", clause="HLP-6.1"))
    for cid in ("foir", "ltv", "score", "valuation", "enquiries", "turnover"):
        c = by.get(cid)
        if c and c["status"] in ("flag",) and not (cid == "score" and c["value"].startswith("No score")):
            deviations.append(dict(text=f"{c['label']}: {c['value']} against {c['threshold']}", clause=c["clause"]))
        if c and cid == "foir" and c["status"] == "fail":
            deviations.append(dict(text=f"{c['label']}: {c['value']} against {c['threshold']}", clause=c["clause"]))

    # what would bring the file within policy
    if by["foir"]["status"] != "pass":
        room = cap / 100 * income - obligations
        ml = max_loan(room, rate, app["tenor_months"])
        options.append(f"Reduce the loan to {lakh(round(ml, -4))} (FOIR at the {cap:.0f}% cap).")
        for extra in (24, 60):
            n = app["tenor_months"] + extra
            age_ok = app["applicant_age"] + n / 12 <= max_age and n <= 360
            if age_ok:
                f2 = 100 * (emi(app["loan_amount"], rate, n) + obligations) / income
                if f2 <= cap:
                    options.append(f"Extend tenor to {n // 12} years: FOIR {f2:.1f}%, still within the age limit.")
                    break
        if co and not app.get("co_applicant_is_co_owner"):
            co_doc = read.get("spouse_salary") or {}
            ci = _num(co_doc.get("net_monthly")) or app["declared_income_co"]
            co_ob = sum(a.get("emi", 0) for a in co_rep.get("accounts", []))
            f3 = 100 * (emi_now + obligations + co_ob) / (income + ci)
            options.append(f"Add {co['full_name']} as co-owner and co-borrower: FOIR {f3:.1f}% (HLP-4.4).")
    if self_emp and aa.get("avg_eod_balance"):
        mitigants.append(f"Average balance of Rs {aa['avg_eod_balance'] / 1e5:,.1f} lakh across accounts over {aa.get('months')} months, no bounces (Account Aggregator).")
    if rel.get("banking_since") and str(rel["banking_since"])[:4] <= "2016":
        mitigants.append(f"Banking with us since {str(rel['banking_since'])[:4]}; existing loans repaid on time.")
    if score and score >= 740:
        mitigants.append(f"Bureau score {score} with no delinquency in 12 months.")

    amount = app["loan_amount"]
    if declines:
        decision, label = "Decline", "Recommend decline"
    elif holds:
        decision = "Hold"
        label = "Hold: refer to RCU" if holds[0]["kind"] == "RCU" else "Hold: legal query"
    elif deviations:
        decision, label = "Refer", "Sanction with deviation: refer to higher authority"
    else:
        decision, label = "Sanction", "Recommend sanction"
    ndev = len(deviations)
    if decision == "Decline":
        authority = "Branch Credit Manager to confirm decline; reasons to be sent to the applicant in writing"
    elif decision == "Hold":
        authority = "Branch Credit Manager (file stays on hold)"
    elif amount > PARAMS["rch_limit"] or ndev >= 2:
        authority = "Zonal Credit Committee"
    elif amount > PARAMS["bcm_limit"] or ndev == 1:
        authority = "Regional Credit Head"
    else:
        authority = "Branch Credit Manager"
    conditions = ["Accept the Key Facts Statement (APR, fees, repayment schedule) before signing (RBI KFS directions).",
                  "Create the mortgage and register it with CERSAI within 30 days.",
                  "Property insurance for the loan tenor with the bank as loss payee."]
    if prop.get("construction_status") == "Under construction":
        conditions.insert(1, "Tripartite agreement with the builder; disbursement linked to construction stage, certified by the bank's engineer.")
    else:
        conditions.insert(1, "Deposit of original title deeds; disbursement directly to the seller's account.")
    if any(h["kind"] == "Legal" for h in holds):
        conditions.insert(0, "Before sanction: NOC and original deeds from the existing lender, CERSAI satisfaction, and a fresh advocate re-vetting.")

    flags = [c for c in checks if c["status"] in ("flag", "fail")]
    rec = dict(decision=decision, label=label, authority=authority, deviations=deviations, holds=holds, declines=[dict(text=f"{c['label']}: {c['value']}", clause=c["clause"]) for c in declines],
               mitigants=mitigants if decision in ("Refer", "Sanction") else [], options=options, conditions=conditions if decision in ("Sanction", "Refer") else [],
               loan_amount=amount, rate=rate, emi=round(emi_now), tenor_months=app["tenor_months"], foir=round(foir, 1), ltv=round(ltv, 1), income=round(income), obligations=round(obligations),
               passed=len([c for c in checks if c["status"] == "pass"]), flagged=len(flags), checks_total=len(checks))
    run.emit(s, "recommendation", **rec)
    run.emit(s, "step_end")
    run.flush_audit()

    # ---------------------------------------------------------------- 6 draft the note
    s = "note"
    run.emit(s, "step_start", title=STEPS[5][1], uses=STEPS[5][2])
    facts = dict(applicant=app["full_name"], occupation=app["occupation_type"], employer=app["employer_name"], city=app["city"], purpose=app["purpose"],
                 property=prop["address"], loan=lakh(amount), tenor_years=app["tenor_months"] // 12, rate=f"{rate:.2f}%", emi=f"Rs {emi_now:,.0f}",
                 income=f"Rs {income:,.0f} ({inc_src})", co_applicant_note=co_note, checks=[{k: c[k] for k in ("label", "value", "threshold", "status", "clause", "detail")} for c in checks],
                 document_findings=doc_findings, recommendation=label, deviations=deviations, holds=holds, options=options, mitigants=mitigants, authority=authority)
    narrative, how = draft_note(facts)
    run.emit(s, "note", text=narrative, how=how)
    run.emit(s, "step_end")

    # ---------------------------------------------------------------- 7 hand off
    s = "handoff"
    run.emit(s, "step_start", title=STEPS[6][1], uses=STEPS[6][2])
    run.emit(s, "handoff", to=app["assigned_officer"], authority=authority,
             text=f"Note for sanction is ready for {app['assigned_officer']}. The officer can edit the note, accept the recommendation or override it with a reason. "
                  + ("Sanction then routes to the " + authority + "." if decision in ("Refer",) else ""))
    run.emit(s, "step_end")
    run.result = dict(run_id=run.run_id, application_id=app_id, recommendation=rec, checks=checks, doc_findings=doc_findings, note=narrative, note_how=how,
                      applicant=app["full_name"], officer=app["assigned_officer"])
    run.emit("handoff", "done", result=run.result)


def _summarise(svc, r):
    if r.get("status") != "OK":
        return "No record found"
    if svc == "kyc":
        return f"PAN {r['pan_status'].lower()}, name match {r['name_match']}%, CKYC found"
    if svc == "bureau":
        rp = r["report"]
        return f"Score {rp['score']}, {len(rp['accounts'])} active loan(s), {rp['enquiries_last_90d']} enquiries in 90 days, max DPD {rp['max_dpd_last_12m']}"
    if svc == "cersai":
        n = len(r["subsisting_charges"])
        return "No subsisting charge on this property" if n == 0 else f"{n} subsisting charge: {r['subsisting_charges'][0]['charge_holder']}"
    if svc == "aa":
        return f"{r['months']} months fetched; average credits Rs {r['avg_monthly_credit']:,.0f}/month; {r['bounces']} bounces"
    if svc == "epfo":
        return f"{r['employer'].title()}, contributions for {r['months_continuous']} continuous months"
    if svc == "gst":
        return f"{r['registration_status']}; turnover Rs {r['turnover_12m'] / 1e5:,.1f} lakh in 12 months; {r['returns_filed_12m']}/12 returns filed"
    return "OK"


NOTE_SYSTEM = (
    "You are a credit analyst at an Indian bank writing the summary paragraph of a Note for Sanction for a home loan. "
    "Write for the sanctioning authority: plain English, 120-170 words, no headings, no bullet points. "
    "Use ONLY the facts provided; never invent numbers, names or documents. Quote figures exactly as given. "
    "After each claim that rests on a policy rule, cite the clause id in square brackets, e.g. [HLP-4.1]. "
    "State the recommendation and the sanctioning authority in the last sentence. Indian conventions: lakh, Rs.")


def draft_note(facts):
    if AI_ENABLED:
        try:
            t0 = time.time()
            text, model = gcp.gemini([json.dumps(facts, default=str)], system=NOTE_SYSTEM, temperature=0.3, timeout=45)
            return text.strip(), dict(mode="gemini", model=model, ms=int((time.time() - t0) * 1000))
        except Exception as e:
            return template_note(facts), dict(mode="fallback", error=str(e)[:200])
    return template_note(facts), dict(mode="offline")


def template_note(f):
    fails = [c for c in f["checks"] if c["status"] in ("flag", "fail")]
    passes = [c for c in f["checks"] if c["status"] == "pass"]
    parts = [f"{f['applicant']} ({f['occupation'].lower()}, {f['employer']}, {f['city']}) seeks {f['loan']} over {f['tenor_years']} years for {f['purpose'].lower()} of {f['property']}.",
             f"Assessed income is {f['income']}; at {f['rate']} the EMI is {f['emi']}."]
    if f.get("co_applicant_note"):
        parts.append(f["co_applicant_note"] + " [HLP-4.4]")
    if passes:
        parts.append("Within policy: " + "; ".join(f"{c['label'].lower()} {c['value']} [{c['clause']}]" for c in passes[:5]) + ".")
    if fails:
        parts.append("Exceptions: " + "; ".join(f"{c['label'].lower()} {c['value']} against {c['threshold']} [{c['clause']}]" for c in fails) + ".")
    for h in f["holds"]:
        parts.append(h["text"] + f" [{h['clause']}]")
    if f["options"]:
        parts.append("To bring the file within policy: " + " ".join(f["options"]))
    parts.append(f"Recommendation: {f['recommendation'].lower()}; sanctioning authority: {f['authority']} [HLP-9.1].")
    return " ".join(parts)


# ------------------------------------------------------------------------------------------ Ask the policy
ASK_SYSTEM = ("You answer questions from bank staff about home-loan credit policy. Use ONLY the clauses provided. "
              "Answer in 2-5 plain sentences and cite clause ids in square brackets. If the clauses do not answer the question, say so and suggest who to ask (credit policy team).")


def ask_policy(question):
    from policy_pack import CLAUSES
    words = set(re.findall(r"[a-z]{3,}", question.lower()))
    scored = sorted(CLAUSES, key=lambda c: -len(words & set(re.findall(r"[a-z]{3,}", (c["title"] + " " + c["text"]).lower()))))
    if AI_ENABLED:
        try:
            ctx = "\n".join(f"[{c['clause_id']}] {c['title']} ({c['document']}): {c['text']}" for c in CLAUSES)
            text, model = gcp.gemini([f"Clauses:\n{ctx}\n\nQuestion: {question}"], system=ASK_SYSTEM, temperature=0.1, timeout=30)
            cited = [c for c in CLAUSES if f"[{c['clause_id']}]" in text or c["clause_id"] in text]
            return dict(answer=text.strip(), clauses=cited[:5] or scored[:2], how=dict(mode="gemini", model=model))
        except Exception as e:
            pass
    top = scored[:3]
    return dict(answer="Closest clauses for your question (AI answer unavailable in offline mode): " + " ".join(f"[{c['clause_id']}] {c['text']}" for c in top[:2]), clauses=top, how=dict(mode="offline"))
