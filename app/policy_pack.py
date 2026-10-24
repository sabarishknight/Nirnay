"""Policy pack: the bank's (illustrative) home-loan credit policy plus the RBI rules it rests on.

Each clause has an id that every agent check cites. Numeric thresholds live in PARAMS so that a
policy change is a data change: the Policy Watch agent swaps parameters and re-screens the pipeline.
The internal policy is invented for the demo; the RBI entries summarise real public circulars and
link to them.
"""

PARAMS = {
    "repo_rate": 5.50,              # RBI MPC, 7 Oct 2026
    "eblr_spread": 2.70,            # bank's spread over repo
    "foir_cap": [(50000, 50.0), (100000, 55.0), (10**12, 60.0)],  # (net monthly income up to, cap %)
    "ltv_cap": [(3000000, 90.0), (7500000, 80.0), (10**12, 75.0)],  # (loan amount up to, cap %)
    "score_floor": 700,
    "score_deviation_floor": 650,
    "max_dpd_12m": 30,
    "max_enquiries_90d": 4,
    "income_variance_pct": 15.0,
    "valuation_variance_pct": 15.0,
    "max_age_at_maturity_salaried": 65,
    "max_age_at_maturity_self_employed": 70,
    "min_net_income": 25000,
    "bcm_limit": 7500000,
    "rch_limit": 20000000,
}

INTERNAL = "Home Loan Credit Policy v4.2 (illustrative)"

CLAUSES = [
    # --- internal credit policy (illustrative) -------------------------------------------------
    dict(clause_id="HLP-2.1", document=INTERNAL, section="Eligibility", title="Age and minimum income",
         text="Applicants must be at least 21 years old at application. The loan must be fully repaid by age 65 for salaried and 70 for self-employed borrowers. Minimum net monthly income is Rs 25,000 for the main applicant."),
    dict(clause_id="HLP-3.1", document=INTERNAL, section="Credit bureau", title="Bureau score thresholds",
         text="A bureau score of 700 or above meets standard policy. Scores from 650 to 699 are a deviation that needs approval one level above the normal sanctioning authority. Below 650 the file is not eligible. New-to-credit applicants (no score) may be considered with a salaried co-applicant or 20% additional margin."),
    dict(clause_id="HLP-3.2", document=INTERNAL, section="Credit bureau", title="Delinquency and write-offs",
         text="No account should show more than 30 days past due in the last 12 months. Any written-off or settled account in the last 36 months makes the file ineligible unless a closure letter and No Dues Certificate are produced."),
    dict(clause_id="HLP-3.4", document=INTERNAL, section="Credit bureau", title="Recent enquiries",
         text="More than 4 hard enquiries in the last 90 days is a flag. The officer must record whether the enquiries relate to this home loan (rate shopping) or to new unsecured borrowing."),
    dict(clause_id="HLP-4.1", document=INTERNAL, section="Repayment capacity", title="FOIR caps",
         text="Fixed Obligation to Income Ratio (FOIR) = (proposed EMI + existing EMIs) / net monthly income. Caps: up to 50% where net monthly income is up to Rs 50,000; 55% for Rs 50,001 to Rs 1,00,000; 60% above Rs 1,00,000. The proposed EMI is computed at the rate applicable on the date of assessment."),
    dict(clause_id="HLP-4.2", document=INTERNAL, section="Repayment capacity", title="Income assessment - salaried",
         text="Net salary is the average of the last 3 months' salary credits in the bank statement, cross-checked with salary slips, Form 16 and EPFO contributions. A variance above 15% between sources must be explained; unexplained variance requires referral to the Risk Containment Unit (RCU)."),
    dict(clause_id="HLP-4.3", document=INTERNAL, section="Repayment capacity", title="Income assessment - self-employed",
         text="Income is the average of the last 2 years' ITR income after tax, plus depreciation. Banking turnover (via Account Aggregator or statements) and GST turnover must be consistent with ITR turnover within 20%."),
    dict(clause_id="HLP-4.4", document=INTERNAL, section="Repayment capacity", title="Co-applicant income",
         text="Income of a co-applicant can be added for FOIR only when the co-applicant is also a co-owner of the property and a co-borrower on the loan."),
    dict(clause_id="HLP-5.1", document=INTERNAL, section="Security", title="Loan-to-value (LTV)",
         text="LTV caps follow RBI: 90% for loans up to Rs 30 lakh, 80% above Rs 30 lakh up to Rs 75 lakh, 75% above Rs 75 lakh. Property value is the lower of agreement value and the empanelled valuer's market value. Stamp duty and registration charges are excluded except for units costing up to Rs 10 lakh."),
    dict(clause_id="HLP-5.3", document=INTERNAL, section="Security", title="Valuation variance",
         text="If agreement value exceeds the valuer's market value by more than 15%, refer the file to the technical head for a second valuation."),
    dict(clause_id="HLP-6.1", document=INTERNAL, section="Legal", title="Title and encumbrance",
         text="A panel advocate's title search report covering at least 30 years, an encumbrance certificate and a CERSAI search are mandatory. Any subsisting charge in favour of another lender must be released (NOC, original title deeds returned, and CERSAI satisfaction filed) before disbursement, except in balance transfer cases where our bank takes over the charge. Where a seller's declaration conflicts with the EC or CERSAI record, the file is held until the panel advocate re-vets the title."),
    dict(clause_id="HLP-6.4", document=INTERNAL, section="Legal", title="Under-construction property",
         text="Under-construction units must be in a RERA-registered project approved by the bank (Approved Project Finance list). Disbursement is linked to construction stage and a tripartite agreement between builder, borrower and bank is required."),
    dict(clause_id="HLP-7.2", document=INTERNAL, section="Fraud control", title="RCU referral",
         text="Mandatory RCU (Risk Containment Unit) sampling applies where documents conflict with independent sources (bank statement, Form 16, EPFO, ITR, GST). Referral is a verification step, not a finding of fraud; the file is on hold until RCU reports."),
    dict(clause_id="HLP-9.1", document=INTERNAL, section="Delegation of powers", title="Sanctioning authority",
         text="Branch Credit Manager (BCM): up to Rs 75 lakh with no deviation. Regional Credit Head (RCH): up to Rs 2 crore, or any amount up to Rs 2 crore with one deviation. Zonal Credit Committee (ZCC): above Rs 2 crore, or two or more deviations. A decline must be confirmed by a human authority and the reasons communicated to the applicant in writing."),
    dict(clause_id="HLP-10.1", document=INTERNAL, section="Pricing", title="Rate card",
         text="Floating rate linked to the external benchmark: EBLR = RBI repo rate + 2.70%. Risk premium over EBLR by bureau score: 775 and above nil; 750-774 0.15%; 700-749 0.35%; 650-699 0.65%; no score 0.50%. Self-employed: additional 0.10%. The rate resets with the repo rate."),
    # --- RBI and statutory references (summaries of real public documents) -----------------------
    dict(clause_id="RBI-LTV", document="RBI Master Circular - Housing Finance; RBI/2020-21/56 Individual Housing Loans - Rationalisation of Risk Weights (16 Oct 2020)", section="Housing finance", title="LTV caps and risk weights",
         text="LTV caps for individual housing loans: 90% up to Rs 30 lakh, 80% above Rs 30 lakh up to Rs 75 lakh, 75% above Rs 75 lakh. Stamp duty and registration charges are not included in property cost for LTV, except for units up to Rs 10 lakh. The 2020 circular links capital risk weight to LTV only: 35% at LTV up to 80%, 50% above 80% up to 90%.",
         source_url="https://www.rbi.org.in/Scripts/NotificationUser.aspx?Id=11984"),
    dict(clause_id="RBI-EBLR-2019", document="RBI/2019-20/53 External Benchmark Based Lending (4 Sep 2019)", section="Pricing", title="External benchmark based lending",
         text="All new floating rate personal and retail loans by banks, including housing loans, must be linked to an external benchmark such as the RBI policy repo rate. The spread over the benchmark stays unchanged unless the borrower's credit assessment changes, and rates reset at least once every three months.",
         source_url="https://www.rbi.org.in/scripts/notificationuser.aspx?id=11677"),
    dict(clause_id="RBI-KFS-2024", document="RBI: Key Facts Statement (KFS) for Loans & Advances (15 Apr 2024)", section="Disclosure", title="Key Fact Statement",
         text="From 1 Oct 2024, every retail and MSME term loan must be offered with a KFS in a standard format showing the Annual Percentage Rate (APR), all fees and charges, the repayment schedule and grievance redressal details, before the loan agreement is executed.",
         source_url="https://rbi.org.in/Scripts/NotificationUser.aspx?Id=12663"),
    dict(clause_id="RBI-DOCS-2023", document="RBI: Responsible Lending Conduct - Release of Movable / Immovable Property Documents (13 Sep 2023)", section="Borrower protection", title="Return of title documents",
         text="On full repayment, the lender must release all original movable or immovable property documents and remove any charge registered with CERSAI within 30 days, failing which it must compensate the borrower at Rs 5,000 per day of delay.",
         source_url="https://www.rbi.org.in/Scripts/NotificationUser.aspx?Id=12535"),
    dict(clause_id="RBI-PREPAY-2025", document="RBI (Pre-payment Charges on Loans) Directions, 2025 (2 Jul 2025)", section="Borrower protection", title="No pre-payment charges on floating rate loans",
         text="For floating rate loans to individuals for non-business purposes, regulated lenders shall not levy any foreclosure or pre-payment charge. Applies to loans sanctioned or renewed from 1 Jan 2026.",
         source_url="https://www.business-standard.com/finance/news/rbi-no-prepayment-charges-loans-mse-bank-small-business-finance-125070201501_1.html"),
    dict(clause_id="SARFAESI-CERSAI", document="SARFAESI Act 2002, s.23 and CERSAI rules", section="Security", title="CERSAI registration",
         text="Every security interest created over property (including equitable mortgage by deposit of title deeds) must be registered with CERSAI within 30 days of creation. Lenders search CERSAI before sanction to detect existing charges on the same property. Search fee Rs 10; registration Rs 50 (loans up to Rs 5 lakh) or Rs 100 (above).",
         source_url="https://www.cersai.org.in"),
    dict(clause_id="RBI-KYC-2016", document="RBI Master Direction - Know Your Customer (KYC) Direction, 2016 (as amended)", section="KYC", title="Customer due diligence",
         text="Banks must verify identity and address using officially valid documents or Aadhaar-based e-KYC with consent, obtain PAN, upload KYC records to the Central KYC Records Registry (CKYCR), and may use Video-based Customer Identification Process (V-CIP).",
         source_url="https://www.rbi.org.in/Scripts/BS_ViewMasterDirections.aspx?id=11566"),
    dict(clause_id="RBI-MPC-OCT26", document="RBI Monetary Policy Statement (7 Oct 2026)", section="Rates", title="Repo rate raised to 5.50%",
         text="The MPC raised the policy repo rate by 25 basis points from 5.25% to 5.50% and changed its stance to calibrated tightening. Repo-linked home loan rates reset upward, raising EMIs of floating rate borrowers and of in-flight applications assessed at the old rate.",
         source_url="https://www.scconline.com/blog/post/2026/10/09/rbi-hikes-repo-rate-to-5-50-percent-october-2026/"),
]

CLAUSE_BY_ID = {c["clause_id"]: c for c in CLAUSES}

# Changes the Policy Watch agent can simulate. Each is a parameter diff + the clause that carries it.
POLICY_EVENTS = [
    dict(event_id="MPC-2026-10", title="RBI raises repo rate 5.25% to 5.50% (7 Oct 2026)", kind="Regulatory",
         clause_id="RBI-MPC-OCT26", before={"repo_rate": 5.25}, after={"repo_rate": 5.50},
         summary="Every repo-linked rate goes up 25 bps. Files assessed before 7 Oct used the old rate, so their EMI and FOIR are understated."),
    dict(event_id="HLP-4.1-v4.3", title="Internal: FOIR cap for incomes up to Rs 50,000 cut from 50% to 45%", kind="Internal policy",
         clause_id="HLP-4.1", before={"foir_cap": [(50000, 50.0), (100000, 55.0), (10**12, 60.0)]}, after={"foir_cap": [(50000, 45.0), (100000, 55.0), (10**12, 60.0)]},
         summary="Credit committee proposal after early-delinquency review of low-income segment."),
    dict(event_id="HLP-3.1-v4.3", title="Internal: bureau score floor raised from 700 to 720", kind="Internal policy",
         clause_id="HLP-3.1", before={"score_floor": 700}, after={"score_floor": 720},
         summary="Proposal to tighten entry criteria in a rising-rate cycle."),
]


def cap_for(table, value):
    for upto, cap in table:
        if value <= upto:
            return cap
    return table[-1][1]


def rate_for(score, self_employed, params=PARAMS):
    eblr = params["repo_rate"] + params["eblr_spread"]
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
    return round(eblr + rp + (0.10 if self_employed else 0.0), 2)


def emi(principal, annual_rate, months):
    i = annual_rate / 1200
    return principal * i * (1 + i) ** months / ((1 + i) ** months - 1)
