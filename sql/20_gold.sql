-- Decision-ready (gold) layer: features the agent and the dashboards read.
-- Rule thresholds mirror Home Loan Credit Policy v4.2 (HLP-*) and the RBI LTV caps.

CREATE OR REPLACE TABLE lending_gold.application_features AS
WITH base AS (
  SELECT
    x.*,
    CASE WHEN x.occupation_type = 'Salaried' AND x.salary_credit_avg_3m IS NOT NULL THEN x.salary_credit_avg_3m ELSE x.declared_income_main END
      + CASE WHEN x.co_applicant_is_co_owner = 1 THEN x.declared_income_co ELSE 0 END AS income_assessed,
    x.bureau_emi + CASE WHEN x.co_applicant_is_co_owner = 1 THEN x.co_bureau_emi ELSE 0 END AS obligations,
    CASE
      WHEN x.bureau_score IS NULL OR x.bureau_score < 0 THEN 0.50
      WHEN x.bureau_score >= 775 THEN 0.0
      WHEN x.bureau_score >= 750 THEN 0.15
      WHEN x.bureau_score >= 700 THEN 0.35
      ELSE 0.65 END
      + CASE WHEN x.occupation_type = 'Salaried' THEN 0.0 ELSE 0.10 END AS risk_premium,
    rl.repo_rate AS repo_at_login,
    rn.repo_rate AS repo_now,
    rn.eblr_spread
  FROM lending_curated.applicant_360 x
  JOIN lending_raw.rate_card rl ON x.received_date >= rl.effective_from AND x.received_date < rl.effective_to
  CROSS JOIN (SELECT repo_rate, eblr_spread FROM lending_raw.rate_card WHERE effective_to = (SELECT MAX(effective_to) FROM lending_raw.rate_card)) rn
),
priced AS (
  SELECT
    b.*,
    ROUND(b.repo_at_login + b.eblr_spread + b.risk_premium, 2) AS rate_at_login,
    ROUND(b.repo_now + b.eblr_spread + b.risk_premium, 2) AS rate_now
  FROM base b
),
emis AS (
  SELECT
    p.*,
    ROUND(p.loan_amount * (p.rate_at_login / 1200) * POWER(1 + p.rate_at_login / 1200, p.tenor_months) / (POWER(1 + p.rate_at_login / 1200, p.tenor_months) - 1), 0) AS emi_at_login,
    ROUND(p.loan_amount * (p.rate_now / 1200) * POWER(1 + p.rate_now / 1200, p.tenor_months) / (POWER(1 + p.rate_now / 1200, p.tenor_months) - 1), 0) AS emi_now,
    CASE WHEN p.income_assessed <= 50000 THEN 50.0 WHEN p.income_assessed <= 100000 THEN 55.0 ELSE 60.0 END AS foir_cap,
    CASE WHEN p.loan_amount <= 3000000 THEN 90.0 WHEN p.loan_amount <= 7500000 THEN 80.0 ELSE 75.0 END AS ltv_cap
  FROM priced p
)
SELECT
  e.application_id, e.customer_id, e.full_name, e.city, e.occupation_type, e.channel, e.received_date, e.stage, e.stage_entered_date,
  e.assigned_officer, e.is_demo_case, e.loan_amount, e.tenor_months, e.purpose, e.property_type, e.construction_status,
  e.income_assessed, e.obligations, e.bureau_score, e.enquiries_last_90d, e.max_dpd_last_12m, e.written_off_or_settled_36m,
  e.repo_at_login, e.repo_now, e.rate_at_login, e.rate_now, e.emi_at_login, e.emi_now,
  ROUND(100.0 * (e.emi_at_login + e.obligations) / e.income_assessed, 1) AS foir_at_login,
  ROUND(100.0 * (e.emi_now + e.obligations) / e.income_assessed, 1) AS foir_now,
  e.foir_cap,
  e.security_value,
  ROUND(100.0 * e.loan_amount / e.security_value, 1) AS ltv,
  e.ltv_cap,
  e.valuation_gap_pct,
  e.cersai_subsisting_charges,
  CASE WHEN e.occupation_type = 'Salaried' AND e.salary_credit_avg_3m IS NOT NULL AND e.declared_income_main > 0
       THEN ROUND(100.0 * (e.declared_income_main - e.salary_credit_avg_3m) / e.declared_income_main, 1) END AS income_variance_pct,
  CASE
    WHEN e.bureau_score >= 0 AND e.bureau_score < 650 THEN 'Not eligible'
    WHEN e.written_off_or_settled_36m = 1 THEN 'Not eligible'
    WHEN e.cersai_subsisting_charges > 0 THEN 'Hold'
    WHEN 100.0 * (e.emi_now + e.obligations) / e.income_assessed > e.foir_cap + 10 THEN 'Not eligible'
    WHEN 100.0 * (e.emi_now + e.obligations) / e.income_assessed > e.foir_cap THEN 'Deviation'
    WHEN 100.0 * e.loan_amount / e.security_value > e.ltv_cap THEN 'Deviation'
    WHEN e.bureau_score >= 650 AND e.bureau_score < 700 THEN 'Deviation'
    ELSE 'Within policy' END AS screening_result
FROM emis e;

CREATE OR REPLACE TABLE lending_gold.stage_tat AS
SELECT
  stage,
  COUNT(*) AS files,
  ROUND(AVG(working_days), 1) AS avg_working_days,
  MAX(working_days) AS max_working_days
FROM lending_raw.los_stage_history
WHERE working_days IS NOT NULL
GROUP BY stage;

CREATE OR REPLACE TABLE lending_gold.override_patterns AS
SELECT
  override_reason,
  agent_recommendation,
  officer_decision,
  COUNT(*) AS cases
FROM lending_raw.officer_decisions_history
WHERE override = 1
GROUP BY override_reason, agent_recommendation, officer_decision;
