"""Data access: BigQuery in the cloud, a SQLite copy of the same lakehouse on a laptop.

Every query the app runs is listed here by name so the UI can show the exact SQL behind each number.
"""
import json, os, re, sqlite3, threading, time
import gcp, lakehouse

MODE = "bigquery" if os.environ.get("GCP_PROJECT") and os.environ.get("USE_BIGQUERY", "1") == "1" else "local"
_local = {"con": None}
_lock = threading.Lock()

Q = {
    "queue": """
SELECT application_id, full_name, city, occupation_type, loan_amount, stage, received_date, stage_entered_date,
       assigned_officer, screening_result, foir_now, foir_cap, ltv, ltv_cap, bureau_score, is_demo_case
FROM lending_gold.application_features
WHERE stage IN ('Login & KYC', 'Credit appraisal', 'Legal & technical', 'Sanction')
ORDER BY is_demo_case DESC, received_date DESC
LIMIT 60""",
    "application": """
SELECT a.*, c.full_name, c.pan, c.dob, c.gender, c.city, c.state, c.occupation_type, c.employer_name, c.employer_category,
       c.uan, c.gstin, c.customer_since, c.cif, c.aadhaar_masked
FROM lending_raw.los_applications a
JOIN lending_raw.core_customers c ON c.customer_id = a.customer_id
WHERE a.application_id = @app_id""",
    "co_applicant": """
SELECT customer_id, full_name, pan, occupation_type, employer_name, uan
FROM lending_raw.core_customers WHERE customer_id = @customer_id""",
    "property": """
SELECT p.*, v.valuer, v.valuation_date, v.market_value, v.realisable_value, v.distress_value, v.remarks AS valuation_remarks,
       l.advocate, l.report_date AS legal_report_date, l.search_years, l.title_status, l.encumbrance, l.remarks AS legal_remarks
FROM lending_raw.properties p
JOIN lending_raw.los_applications a ON a.property_id = p.property_id
LEFT JOIN lending_raw.valuation_reports v ON v.application_id = a.application_id
LEFT JOIN lending_raw.legal_reports l ON l.application_id = a.application_id
WHERE a.application_id = @app_id""",
    "relationship": """
SELECT
  (SELECT COUNT(*) FROM lending_raw.core_accounts WHERE customer_id = @customer_id) AS accounts,
  (SELECT SUM(avg_monthly_balance_6m) FROM lending_raw.core_accounts WHERE customer_id = @customer_id) AS avg_balance_6m,
  (SELECT MIN(open_date) FROM lending_raw.core_accounts WHERE customer_id = @customer_id) AS banking_since,
  (SELECT COUNT(*) FROM lending_raw.core_loans WHERE customer_id = @customer_id) AS loans_with_bank,
  (SELECT SUM(emi) FROM lending_raw.core_loans WHERE customer_id = @customer_id) AS emi_with_bank""",
    "repayment": """
SELECT l.loan_id, l.product, l.emi, l.outstanding, MAX(r.dpd) AS max_dpd_12m, SUM(CASE WHEN r.dpd = 0 THEN 1 ELSE 0 END) AS months_on_time
FROM lending_raw.core_loans l
JOIN lending_raw.core_repayments r ON r.loan_id = l.loan_id
WHERE l.customer_id = @customer_id
GROUP BY l.loan_id, l.product, l.emi, l.outstanding""",
    "bank_income": """
SELECT salary_credit_avg_3m, total_credits_avg_6m, emi_debits_avg_6m, cheque_bounces_12m, months_of_data
FROM lending_curated.bank_income WHERE customer_id = @customer_id""",
    "features": """
SELECT * FROM lending_gold.application_features WHERE application_id = @app_id""",
    "documents_index": """
SELECT doc_type, received_date, pages, source FROM lending_raw.los_documents WHERE application_id = @app_id ORDER BY doc_type""",
    "dash_pipeline": """
SELECT stage, COUNT(*) AS files, SUM(loan_amount) AS amount
FROM lending_gold.application_features
GROUP BY stage""",
    "dash_screening": """
SELECT screening_result, COUNT(*) AS files, SUM(loan_amount) AS amount
FROM lending_gold.application_features
WHERE stage IN ('Login & KYC', 'Credit appraisal', 'Legal & technical', 'Sanction')
GROUP BY screening_result""",
    "dash_tat": """
SELECT stage, files, avg_working_days, max_working_days FROM lending_gold.stage_tat""",
    "dash_overrides": """
SELECT COUNT(*) AS decisions, SUM(override) AS overrides FROM lending_raw.officer_decisions_history""",
    "dash_override_patterns": """
SELECT override_reason, agent_recommendation, officer_decision, cases FROM lending_gold.override_patterns ORDER BY cases DESC""",
    "dash_live_decisions": """
SELECT application_id, decided_at, agent_recommendation, officer_decision, override, override_reason, decided_by
FROM lending_gold.officer_decisions ORDER BY decided_at DESC LIMIT 20""",
    "dash_channel": """
SELECT channel, COUNT(*) AS files, ROUND(AVG(loan_amount), 0) AS avg_ticket
FROM lending_gold.application_features GROUP BY channel""",
    "rescreen": """
-- Policy Watch: re-screen every in-flight file under the old and the new parameters
WITH f AS (
  SELECT application_id, full_name, city, stage, received_date, loan_amount, tenor_months, income_assessed, obligations, bureau_score,
         rate_now - repo_now AS margin
  FROM lending_gold.application_features
  WHERE stage IN ('Login & KYC', 'Credit appraisal', 'Legal & technical', 'Sanction')
),
r AS (
  SELECT f.*,
    (f.margin + @repo_before) / 1200 AS i0,
    (f.margin + @repo_after) / 1200 AS i1,
    CASE WHEN f.income_assessed <= 50000 THEN @cap_low_before WHEN f.income_assessed <= 100000 THEN 55.0 ELSE 60.0 END AS cap0,
    CASE WHEN f.income_assessed <= 50000 THEN @cap_low_after WHEN f.income_assessed <= 100000 THEN 55.0 ELSE 60.0 END AS cap1
  FROM f
),
e AS (
  SELECT r.*,
    100.0 * (r.loan_amount * r.i0 * POWER(1 + r.i0, r.tenor_months) / (POWER(1 + r.i0, r.tenor_months) - 1) + r.obligations) / r.income_assessed AS foir0,
    100.0 * (r.loan_amount * r.i1 * POWER(1 + r.i1, r.tenor_months) / (POWER(1 + r.i1, r.tenor_months) - 1) + r.obligations) / r.income_assessed AS foir1
  FROM r
)
SELECT application_id, full_name, city, stage, received_date, loan_amount, bureau_score,
  ROUND(foir0, 1) AS foir_before, ROUND(foir1, 1) AS foir_after, cap0 AS cap_before, cap1 AS cap_after,
  CASE WHEN foir0 <= cap0 AND bureau_score >= @floor_before THEN 'Within policy' ELSE 'Outside policy' END AS status_before,
  CASE WHEN foir1 <= cap1 AND bureau_score >= @floor_after THEN 'Within policy' ELSE 'Outside policy' END AS status_after
FROM e
ORDER BY foir1 - cap1 DESC""",
}


def _local_con():
    with _lock:
        if _local["con"] is None:
            d = os.environ.get("LOCAL_DB_DIR", "/tmp/nirnay_db")
            _local["con"] = lakehouse.build_local(d)
        return _local["con"]


def sql_text(name):
    return Q[name].strip()


def query(name, **params):
    sql = Q[name]
    if MODE == "bigquery":
        rows, meta = gcp.bq_query(sql, params)
    else:
        t0 = time.time()
        con = _local_con()
        with _lock:
            cur = con.execute(re.sub(r"@(\w+)", r":\1", sql), params)
            rows = [dict(r) for r in cur.fetchall()]
        meta = dict(engine="SQLite stand-in (local)", ms=int((time.time() - t0) * 1000), bytes_processed=None)
    meta["query_name"] = name
    meta["sql"] = sql.strip()
    return rows, meta


def one(name, **params):
    rows, meta = query(name, **params)
    return (rows[0] if rows else None), meta


def insert(dataset, table, rows):
    if not rows:
        return
    if MODE == "bigquery":
        try:
            gcp.bq_insert(dataset, table, rows)
        except Exception as e:  # audit must not break the demo; surface in logs
            print("audit insert failed", e)
        return
    con = _local_con()
    cols = list(rows[0].keys())
    with _lock:
        con.executemany(f"INSERT INTO {dataset}.{table} ({','.join(cols)}) VALUES ({','.join('?' * len(cols))})",
                        [[json.dumps(r[c]) if isinstance(r[c], (dict, list)) else r[c] for c in cols] for r in rows])
        con.commit()
