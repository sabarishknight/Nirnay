-- Curated (silver) layer: cleaned, joined, one row per business entity.
-- Written in a portable SQL subset so the same file runs in BigQuery and in the local SQLite stand-in.
-- {M3} = first month of the last 3 complete months, {M6} = first month of the last 6.

CREATE OR REPLACE TABLE lending_curated.bank_income AS
SELECT
  a.customer_id,
  ROUND(AVG(CASE WHEN t.month >= '{M3}' AND t.salary_credit > 0 THEN t.salary_credit END), 0) AS salary_credit_avg_3m,
  ROUND(AVG(CASE WHEN t.month >= '{M6}' THEN t.total_credits END), 0) AS total_credits_avg_6m,
  ROUND(AVG(CASE WHEN t.month >= '{M6}' THEN t.emi_debits END), 0) AS emi_debits_avg_6m,
  SUM(t.cheque_bounces) AS cheque_bounces_12m,
  COUNT(DISTINCT t.month) AS months_of_data
FROM lending_raw.core_accounts a
JOIN lending_raw.core_txn_monthly t ON t.account_id = a.account_id
GROUP BY a.customer_id;

CREATE OR REPLACE TABLE lending_curated.bureau_summary AS
SELECT
  c.customer_id,
  b.score AS bureau_score,
  b.enquiries_last_90d,
  b.max_dpd_last_12m,
  b.written_off_or_settled_36m,
  b.tradelines,
  b.total_emi AS bureau_emi
FROM lending_raw.core_customers c
JOIN lending_raw.ext_bureau b ON b.pan = c.pan;

CREATE OR REPLACE TABLE lending_curated.repayment_track AS
SELECT
  l.customer_id,
  COUNT(DISTINCT l.loan_id) AS loans_with_bank,
  SUM(CASE WHEN r.dpd > 0 THEN 1 ELSE 0 END) AS months_with_dpd_12m,
  MAX(r.dpd) AS max_dpd_with_bank_12m
FROM lending_raw.core_loans l
JOIN lending_raw.core_repayments r ON r.loan_id = l.loan_id
GROUP BY l.customer_id;

CREATE OR REPLACE TABLE lending_curated.security AS
SELECT
  p.property_id,
  p.city,
  p.property_type,
  p.construction_status,
  p.rera_number,
  p.agreement_value,
  v.market_value,
  CASE WHEN v.market_value IS NOT NULL AND v.market_value < p.agreement_value THEN v.market_value ELSE p.agreement_value END AS security_value,
  CASE WHEN v.market_value IS NULL THEN NULL ELSE ROUND(100.0 * (p.agreement_value - v.market_value) / v.market_value, 1) END AS valuation_gap_pct,
  COALESCE(cs.subsisting_charges, 0) AS cersai_subsisting_charges,
  l.title_status
FROM lending_raw.properties p
JOIN lending_raw.los_applications a ON a.property_id = p.property_id
LEFT JOIN lending_raw.valuation_reports v ON v.application_id = a.application_id
LEFT JOIN lending_raw.legal_reports l ON l.application_id = a.application_id
LEFT JOIN lending_raw.ext_cersai cs ON cs.property_id = p.property_id;

CREATE OR REPLACE TABLE lending_curated.applicant_360 AS
SELECT
  a.application_id,
  a.customer_id,
  c.full_name,
  c.city,
  c.occupation_type,
  c.employer_name,
  c.employer_category,
  a.applicant_age,
  a.co_applicant_id,
  a.co_applicant_is_co_owner,
  a.channel,
  a.received_date,
  a.loan_amount,
  a.tenor_months,
  a.purpose,
  a.stage,
  a.stage_entered_date,
  a.assigned_officer,
  a.is_demo_case,
  a.declared_income_main,
  a.declared_income_co,
  bi.salary_credit_avg_3m,
  bi.total_credits_avg_6m,
  bi.cheque_bounces_12m,
  bs.bureau_score,
  bs.enquiries_last_90d,
  bs.max_dpd_last_12m,
  bs.written_off_or_settled_36m,
  COALESCE(bs.bureau_emi, 0) AS bureau_emi,
  COALESCE(cob.bureau_emi, 0) AS co_bureau_emi,
  COALESCE(rt.max_dpd_with_bank_12m, 0) AS max_dpd_with_bank_12m,
  s.property_type,
  s.construction_status,
  s.agreement_value,
  s.market_value,
  s.security_value,
  s.valuation_gap_pct,
  s.cersai_subsisting_charges,
  s.title_status
FROM lending_raw.los_applications a
JOIN lending_raw.core_customers c ON c.customer_id = a.customer_id
LEFT JOIN lending_curated.bank_income bi ON bi.customer_id = a.customer_id
LEFT JOIN lending_curated.bureau_summary bs ON bs.customer_id = a.customer_id
LEFT JOIN lending_curated.bureau_summary cob ON cob.customer_id = a.co_applicant_id
LEFT JOIN lending_curated.repayment_track rt ON rt.customer_id = a.customer_id
LEFT JOIN lending_curated.security s ON s.property_id = a.property_id;
