"""
The 37-target metric dictionary for POC2.

Each entry carries:
  - `name`   — canonical target label (also the dictionary key the model
               must echo verbatim in `metric_target`).
  - `type`   — "Currency" | "Percentage" | "Boolean". Drives the value-format
               sanity check at parse time.
  - `accept` — Common Printed Variants the prompt should SEEK. Illustrative,
               not exhaustive — the model may still recognize unlisted
               semantic equivalents.
  - `reject` — Look-Alikes That Are NOT This Metric. CLOSED and BINDING:
               if the printed label semantically matches any of these, OMIT.

Lifted from the user's POC2 prototype; ordering preserved so the loop output
is stable and the UI's coverage table reads predictably (Class A → G).
"""
from __future__ import annotations

from typing import Literal, TypedDict


MetricType = Literal["Currency", "Percentage", "Boolean"]


class MetricDef(TypedDict):
    name: str
    type: MetricType
    accept: list[str]
    reject: list[str]
    definition: str



METRIC_METADATA: list[MetricDef] = [
    {
        "name": "Adjusted Revenue",
        "type": "Currency",
        "accept": ["Adjusted Revenue", "Normalized Revenue", "Pro-forma Revenue", "Core Revenue", "Non-GAAP Revenue", "Underlying Revenue"],
        "reject": ["Reported Revenue", "Total Revenue", "Net Revenue", "Operating Revenue", "Revenue from Operations", "Constant Currency Revenue", "Revenue Growth %", "Adjusted EBITDA"],
        "definition": (
            "Revenue adjusted by management for one-time events, non-recurring items, or "
            "discontinued operations to show core top-line performance.\n"
            "DISCRIMINATOR RULES:\n"
            "- VALUE TYPE: Absolute Currency (a top-line figure, NEVER a percentage and NEVER a growth rate).\n"
            "- BASIS: Adjusted/Normalized/Pro-forma/Core/Non-GAAP — the printed label MUST carry one of these qualifiers attached to Revenue. Look for explicit 'Adjusted Revenue' table or reconciliation.\n"
            "- NEVER MAP TO THIS BUCKET: plain 'Revenue' / 'Total Revenue' / 'Reported Revenue' / 'Net Revenue' / 'Revenue from Operations' (those are statutory unadjusted figures with no dedicated bucket — return null per the QUALIFIERS rule); 'Constant Currency Revenue' (FX-neutral, separate bucket); any percentage revenue growth rate."
        ),
        "layer2_rules": (
            "MANDATORY STEP-BY-STEP VERIFICATION:\n"
            "1. STEP 1 (EVIDENCE OF ADJUSTMENT): You are evaluating Adjusted Revenue. The candidate MUST explicitly adjust statutory revenue for unusual, one-time, non-recurring, or discontinued operations.\n"
            "2. STEP 2 (REJECTION OF STATUTORY REVENUE): Do NOT grab statutory unadjusted Revenue from Operations or Total Revenue!"
        ),
    },
    {
        "name": "Adjusted Earnings",
        "type": "Currency",
        "accept": ["Adjusted PAT", "Adjusted Earnings", "Adjusted Net Income", "Adjusted Net Profit", "Adjusted Profit After Tax", "Underlying Earnings", "Underlying PAT"],
        "reject": ["Reported PAT", "Net Profit", "Net Income", "PAT", "Basic Earnings", "Normalized Earnings", "Normalized PAT", "Core Earnings", "Core PAT", "Recurring Earnings", "Adjusted EPS", "Adjusted EBIT", "Adjusted EBITDA"],
        "definition": (
            "The bottom-line profit after adjusting for non-cash items, exceptional costs, and tax anomalies.\n"
            "DISCRIMINATOR RULES:\n"
            "- VALUE TYPE: Absolute Currency (a total Rs/USD bottom-line figure — NEVER per-share, NEVER a percentage).\n"
            "- BASIS: Adjusted — the printed label MUST carry the qualifier 'Adjusted' or 'Underlying' attached to PAT / Earnings / Net Profit / Net Income. Look for explicit presentation in highlights or reconciliations.\n"
            "- NEVER MAP TO THIS BUCKET: Reported PAT / Net Profit / Net Income / Basic Profit (statutory, never adjusted); 'Normalized X' (→ Normalized Earnings), 'Core X' (→ Core Earnings), 'Recurring X' (→ Recurring Earnings) — route by the literal qualifier word on the page; Adjusted EPS (per-share, separate bucket); Adjusted EBIT / Adjusted EBITDA (operating-level, separate buckets)."
        ),
        "layer2_rules": (
            "MANDATORY STEP-BY-STEP VERIFICATION:\n"
            "1. STEP 1 (EVIDENCE OF ADJUSTMENT): You are evaluating Adjusted Earnings (PAT / Net Income adjusted for one-time, non-recurring, or exceptional items). The candidate MUST explicitly show adjustments.\n"
            "2. STEP 2 (REJECTION OF STATUTORY PAT): Do NOT grab statutory unadjusted Net Profit or Reported PAT!"
        ),
    },
    {
        "name": "Normalized Earnings",
        "type": "Currency",
        "accept": [
            "Normalized Earnings", "Normalized PAT", "Normalized Net Income", "Normalized Profit", 
            "Normalized Profit After Tax", "PAT (Normalized)", "Normalized Net Profit", 
            "Normalized PAT attributable to equity shareholders", "Normalized Net Income attributable to shareholders of the parent",
            "PAT before exceptional items (net of tax)", "Net profit before exceptional items after tax", 
            "Normalized Net Profit (ex-one offs)", "Pro-forma Normalized Net Income"
        ],
        "reject": [
            "Adjusted Earnings", "Adjusted PAT", "Core Earnings", "Core PAT", "Recurring Earnings", 
            "Reported PAT", "Net Profit", "Net Income", "Basic Earnings", "Normalized EPS", 
            "Normalized EBITDA", "Normalized Credit Cost", "Normalized PBT", "Normalized Profit Before Tax", 
            "Normalized EBT", "Normalized Operating Profit", "Normalized EBIT", "Total Comprehensive Income", 
            "Comprehensive Income (Normalized)", "Other Comprehensive Income", "Normalized Segment Profit"
        ],
        "definition": (
            "Earnings calculated by smoothing out fluctuations, non-recurring anomalies, or one-off exceptional items to reflect a 'steady-state' bottom-line profit level after tax.\n"
            "DISCRIMINATOR RULES:\n"
            "- VALUE TYPE: Absolute Currency at the bottom-line post-tax level (a total Rs/USD figure — NEVER per-share, NEVER pre-tax PBT, NEVER a percentage).\n"
            "- BASIS: Normalized — the printed label MUST literally contain 'Normalized' attached to Earnings / PAT / Net Income / Net Profit, OR represent statutory Net Profit after tax explicitly adjusted to exclude one-off exceptional items (`PAT before exceptional items net of tax`).\n"
            "- NEVER MAP TO THIS BUCKET: 'Adjusted X' (→ Adjusted Earnings) and 'Core X' / 'Recurring X' (separate buckets) — route by the exact qualifier word on the page; Reported PAT / Net Income (statutory unadjusted); Normalized EPS (per-share); Normalized EBITDA / Normalized PBT (pre-tax or pre-D&A concepts); Total Comprehensive Income (`OCI` inclusion)."
        ),
        "layer2_rules": (
            "MANDATORY STEP-BY-STEP ACCOUNTING & SCOPE VERIFICATION:\n"
            "1. STEP 1 (🚨 POST-TAX & POST-INTEREST FIREWALL - CRITICAL): ACTIVATE KNOWLEDGE of Ind AS Schedule III P&L Structure. You are evaluating Normalized Earnings (`Normalized PAT / Net Income`). The candidate MUST be after subtracting both Finance Costs (`Interest`) and Income Tax (`Current & Deferred Tax`)! If a candidate is labeled 'Normalized PBT', 'Normalized Profit Before Tax', 'Profit before exceptional items and tax', or 'Normalized Operating Profit', you MUST STRICTLY REJECT IT!\n"
            "2. STEP 2 (TAX-EFFECTED EXCEPTIONAL ITEMS CHECK): ACTIVATE KNOWLEDGE of Ind AS 33/34. If the figure is derived from statutory profit by removing Exceptional Items, verify that the tax impact of the exceptional item was applied (e.g., 'PAT before exceptional items (net of tax)' or 'Net Profit excluding exceptional items after tax'). Do not grab pre-tax exceptional adjustments.\n"
            "3. STEP 3 (OCI & COMPREHENSIVE INCOME EXCLUSION): ACTIVATE KNOWLEDGE of Ind AS 1. Strictly reject 'Total Comprehensive Income' or 'Other Comprehensive Income (OCI)'. Normalized Earnings corresponds strictly to Net Profit (`PAT`) attributable to equity shareholders.\n"
            "4. STEP 4 (DUAL-SCOPE ENFORCEMENT): For Consolidated scope, select group-level Normalized PAT attributable to owners of the parent. Strictly reject standalone parent 'Normalized PAT before dividend from subsidiaries' or Note 38/54 segment profit."
        ),
    },
    {
        "name": "Core Earnings",
        "type": "Currency",
        "accept": [
            "Core Earnings", "Core PAT", "Core Net Income", "Core Profit", "Underlying Profit", 
            "Core Net Profit", "Underlying PAT", "Underlying Net Income", "PAT from core operations", 
            "Net Profit from core operations", "Core PAT attributable to equity shareholders", 
            "Core Net Profit (excluding treasury income)", "Underlying Net Income attributable to shareholders"
        ],
        "reject": [
            "Adjusted Earnings", "Normalized Earnings", "Recurring Earnings", "Net Income", "Net Profit", 
            "Reported PAT", "EBITDA", "Core Operating Profit", "Core Margin", "Base Business Margin", 
            "Core Revenue", "Core PBT", "Underlying Profit Before Tax", "Core Profit Before Tax", 
            "Core EBITDA", "Underlying EBITDA", "Segment Core Profit", "Treasury Income", "Other Income"
        ],
        "definition": (
            "Profit after tax derived strictly and solely from primary, core business operations, excluding non-operating investment income, treasury gains/losses, dividend income, or secondary segments.\n"
            "DISCRIMINATOR RULES:\n"
            "- VALUE TYPE: Absolute Currency at the bottom-line post-tax earnings level (`PAT / Net Income` — NEVER a margin percentage, NEVER operating-profit/EBIT level, NEVER per-share).\n"
            "- BASIS: Core/Underlying — the printed label MUST literally contain 'Core' or 'Underlying' attached to Earnings / PAT / Profit / Net Income, OR represent statutory `PAT from core operations`.\n"
            "- NEVER MAP TO THIS BUCKET: 'Adjusted X' / 'Normalized X' / 'Recurring X' (route by exact qualifier — each is its own bucket); plain Net Income / Reported PAT (statutory unadjusted); EBITDA; 'Core Operating Profit' / 'Core EBIT' (operating-level, separate bucket); pre-tax 'Core PBT'; Core Margin."
        ),
        "layer2_rules": (
            "MANDATORY STEP-BY-STEP ACCOUNTING & SCOPE VERIFICATION:\n"
            "1. STEP 1 (🚨 BOTTOM-LINE POST-TAX VERIFICATION - CRITICAL): ACTIVATE KNOWLEDGE of Ind AS Schedule III. You are evaluating Core Earnings (`Core PAT / Core Net Income`). Confirm that the candidate represents bottom-line profit AFTER subtracting both Depreciation, Finance Costs (`Interest`), and Income Tax! If the candidate is labeled 'Core Operating Profit', 'Core EBIT', 'Underlying Operating Profit', or 'Core PBT / Underlying Profit Before Tax', you MUST STRICTLY REJECT IT!\n"
            "2. STEP 2 (PROOF OF NON-OPERATING / TREASURY EXCLUSION): ACTIVATE KNOWLEDGE of Schedule III Note 26/29. Confirm that the figure excludes non-operating income (`Note 26/29 Other Income`), treasury investment gains/losses (`Ind AS 109 fair value changes`), or one-off capital gains on property/investments.\n"
            "3. STEP 3 (DUAL-SCOPE ENFORCEMENT): For Consolidated scope, select group-level Core PAT attributable to shareholders. Strictly reject standalone parent 'Core PAT excluding dividend from subsidiaries' or Note 38/54 segment core profit."
        ),
    },
    {
        "name": "Recurring Earnings",
        "type": "Currency",
        "accept": [
            "Recurring Earnings", "Recurring PAT", "Recurring Profit", "Recurring Net Income", 
            "Recurring Net Profit", "Recurring PAT attributable to equity holders", 
            "Net Profit from recurring operations", "PAT from recurring operations", 
            "Recurring Net Income (Non-GAAP)"
        ],
        "reject": [
            "Adjusted Earnings", "Normalized Earnings", "Core Earnings", "Implied Earnings", 
            "Forecasted Earnings", "Projected Earnings", "Net Profit", "Net Income", "Reported PAT", 
            "Recurring Operating Profit", "Recurring EBIT", "Recurring EBITDA", "Recurring PBT", 
            "Recurring Profit Before Tax", "Profit from continuing operations (if exceptional items present)", 
            "Recurring Segment Profit"
        ],
        "definition": (
            "Earnings expected to repeat reliably in future periods, strictly excluding non-recurring windfalls, exceptional gains/losses, or one-off accounting impacts.\n"
            "DISCRIMINATOR RULES:\n"
            "- VALUE TYPE: Absolute Currency at the bottom-line post-tax level (`PAT / Net Income` — NEVER a percentage, NEVER per-share, NEVER pre-tax).\n"
            "- BASIS: Recurring — the printed label MUST literally contain 'Recurring' attached to Earnings / PAT / Profit / Net Income, OR represent profit after tax explicitly adjusted to eliminate non-recurring items.\n"
            "- NEVER MAP TO THIS BUCKET: 'Adjusted X' / 'Normalized X' / 'Core X' (separate buckets — match literal qualifier); forecasted/implied/projected earnings (forward-looking estimates); plain Net Profit / Reported PAT (statutory); 'Profit from continuing operations' if statutory Exceptional Items exist on the P&L; operating-level 'Recurring EBIT/EBITDA'."
        ),
        "layer2_rules": (
            "MANDATORY STEP-BY-STEP ACCOUNTING & SCOPE VERIFICATION:\n"
            "1. STEP 1 (🚨 CONTINUING OPERATIONS VS. RECURRING EARNINGS FIREWALL - CRITICAL): ACTIVATE KNOWLEDGE of Ind AS 1 (Presentation of Financial Statements). Do NOT blindly select statutory 'Profit / (loss) from continuing operations' from the Statement of Profit and Loss! Check if the P&L reports any 'Exceptional Items' (`Note 33/34`). If Exceptional Items != 0, statutory profit from continuing operations still includes those non-recurring items and MUST BE STRICTLY REJECTED unless management presents a specific table adjusting them out to show 'Recurring PAT'!\n"
            "2. STEP 2 (POST-TAX & POST-INTEREST PROOF): Confirm the figure represents bottom-line profit after subtracting both Finance Costs and Income Tax. Reject pre-tax 'Recurring PBT' or 'Recurring Operating Profit'.\n"
            "3. STEP 3 (ACTUALS VS. PROJECTIONS): Strictly reject forward-looking guidance, projected, or implied earnings. Must represent actual historical recurring profit for the target FY.\n"
            "4. STEP 4 (DUAL-SCOPE ENFORCEMENT): For Consolidated scope, select group-level Recurring PAT. Reject Standalone parent or segment sub-slices."
        ),
    },
    {
        "name": "Adjusted EPS",
        "type": "Currency",
        "accept": ["Adjusted EPS", "Adjusted Earnings Per Share", "Underlying EPS", "Adjusted Diluted EPS"],
        "reject": ["Basic EPS", "Diluted EPS", "Reported EPS", "Normalized EPS", "Cash EPS", "Adjusted Earnings", "Adjusted PAT", "Adjusted Net Income"],
        "definition": (
            "Earnings Per Share calculated using Adjusted Earnings divided by the weighted-average number of shares.\n"
            "DISCRIMINATOR RULES:\n"
            "- VALUE TYPE: Per-Share Currency (a small Rs/USD figure per share — typically single or low-double digits; NEVER a total company figure in millions/billions).\n"
            "- BASIS: Adjusted — the printed label MUST literally contain 'Adjusted' or 'Underlying' attached to EPS / Earnings Per Share.\n"
            "- NEVER MAP TO THIS BUCKET: Basic EPS / Diluted EPS / Reported EPS (statutory, never adjusted); Normalized EPS (→ Normalized EPS — separate bucket); Cash EPS; Adjusted Earnings / Adjusted PAT / Adjusted Net Income (those are the absolute total currency figures, NOT per-share)."
        ),
        "layer2_rules": (
            "MANDATORY STEP-BY-STEP VERIFICATION:\n"
            "1. STEP 1 (PER-SHARE VALUE CHECK): Confirm that the candidate is a per-share figure (e.g. Rs. 15.40 per share), NEVER a total currency aggregate in Crores/Millions!\n"
            "2. STEP 2 (ADJUSTMENT PROOF): Confirm that the figure explicitly adjusts statutory Basic or Diluted EPS for unusual, non-recurring, or exceptional items. Do NOT grab statutory Basic/Diluted EPS if it has not been adjusted!"
        ),
    },
    {
        "name": "Normalized EPS",
        "type": "Currency",
        "accept": [
            "Normalized EPS", "Normalized Earnings Per Share", "Normalized Diluted EPS", 
            "Normalized Basic EPS", "EPS (Normalized)", "Normalized EPS (diluted)", 
            "Normalized Earnings Per Share (Basic)", "Normalized EPS excluding exceptional items", 
            "EPS before exceptional items (diluted)", "Underlying Diluted EPS", "Core Diluted EPS"
        ],
        "reject": [
            "Reported EPS", "Basic EPS", "Diluted EPS", "Adjusted EPS", "Adjusted Diluted EPS", 
            "Cash EPS", "CEPS", "Normalized Earnings", "Normalized PAT", "Normalized Net Income", 
            "Segment EPS", "Dividend Per Share", "Book Value Per Share"
        ],
        "definition": (
            "Earnings Per Share calculated using Normalized Earnings (`PAT before one-off exceptional items net of tax`) divided by the weighted-average number of equity shares, providing a comparable per-share baseline across reporting periods.\n"
            "DISCRIMINATOR RULES:\n"
            "- VALUE TYPE: Per-Share Currency (a small Rs/USD figure per share — typically single or double digits; NEVER a total company figure in Crores/Millions).\n"
            "- BASIS: Normalized — the printed label MUST literally contain 'Normalized' / 'Underlying' attached to EPS / Earnings Per Share, OR represent `EPS before exceptional items` derived from tax-effected normalized earnings.\n"
            "- NEVER MAP TO THIS BUCKET: Adjusted EPS (`→ Adjusted EPS` — match exact qualifier); Basic / Diluted EPS (`statutory unadjusted Ind AS 33 figures`); Normalized Earnings (`total absolute company profit`); Cash EPS (`[PAT + D&A] / Shares`)."
        ),
        "layer2_rules": (
            "MANDATORY STEP-BY-STEP ACCOUNTING & SCOPE VERIFICATION:\n"
            "1. STEP 1 (PER-SHARE VALUE CHECK): Confirm that the candidate is a per-share currency figure (e.g., `Rs. 45.20 per share`), NEVER a total company earnings aggregate in Crores/Lakhs/Millions!\n"
            "2. STEP 2 (NORMALIZATION & TAX PROOF): ACTIVATE KNOWLEDGE of Ind AS 33. Confirm that the figure explicitly adjusts statutory Basic or Diluted EPS for one-time, non-recurring, or exceptional items net of tax. Do NOT grab statutory unadjusted Basic EPS or Diluted EPS from Note 36/37!\n"
            "3. STEP 3 (BASIC VS. DILUTED HIERARCHY): If both Normalized Basic EPS and Normalized Diluted EPS are harvested for the target scope, strictly prefer **Normalized Diluted EPS** (`or Normalized Basic EPS if Diluted is not reported`).\n"
            "4. STEP 4 (DUAL-SCOPE ENFORCEMENT): For Consolidated scope, verify that the per-share figure is derived from Consolidated Normalized Earnings divided by Consolidated weighted-average shares. Strictly reject Standalone parent Normalized EPS."
        ),
    },
    {
        "name": "GAAP One-time Adjustment",
        "type": "Currency",
        "accept": ["GAAP one-time adjustment", "One-time GAAP adjustment", "Exceptional GAAP adjustment", "Non-recurring GAAP item (with numeric value)", "US GAAP reconciliation adjustment", "Ind AS transition adjustment", "IFRS reconciliation impact"],
        "reject": ["Narrative-only descriptions", "Generic exceptional items (no GAAP context)", "Standard P&L Exceptional Items (without reconciliation bridge)", "Ongoing/recurring adjustments", "GAAP Adjusted (the full adjusted figure)", "Adjusted Earnings"],
        "definition": (
            "Explicit numerical adjustments made inside a formal GAAP / Ind AS / IFRS accounting transition reconciliation bridge, accounting policy differential schedule, or management Non-GAAP normalization table.\n"
            "DISCRIMINATOR RULES (`STATUTORY RECONCILIATION VS. REGULAR P&L EXCEPTIONAL ITEMS`):\n"
            "- VALUE TYPE: Absolute Currency adjustment amount with an explicit numeric value (NEVER a narrative-only description).\n"
            "- BASIS: Must explicitly state 'GAAP' or come from a formal 'Non-GAAP / US GAAP / Ind AS / IFRS Reconciliation Schedule' — one-time / exceptional in nature.\n"
            "- NEVER MAP TO THIS BUCKET: Standard 'Exceptional Items' on the face of the audited Ind AS / IFRS Statement of Profit & Loss (Ind AS 1 line items like impairment, VRS, or divestment gain belong to operating/PBT reporting unless presented inside an explicit GAAP reconciliation bridge); full Adjusted Earnings / Adjusted EBITDA aggregates; ongoing recurring adjustments; the GAAP Adjusted post-reconciliation total (→ GAAP Adjusted)."
        ),
        "layer2_rules": (
            "EVIDENCE OF STATUTORY GAAP ADJUSTMENT / RECONCILIATION REQUIREMENT: You are evaluating GAAP One-time Adjustment. The candidate MUST explicitly contain the wording 'GAAP' (or come from a formal Non-GAAP / US GAAP / IFRS / Ind AS Reconciliation Table or transition bridge). STRICTLY REJECT routine P&L 'Exceptional Items' or statutory non-recurring operating expenses unless the company explicitly presents them as part of a formal GAAP accounting reconciliation bridge or management normalization table.\n"
            "PROOF OF EXCLUSIONS: Do not select regular recurring operating expenses or statutory depreciation."
        ),
    },
    {
        "name": "GAAP Adjusted",
        "type": "Currency",
        "accept": [
            "GAAP Pro-forma", "GAAP Normalized", "GAAP Adjusted", "GAAP-Adjusted Earnings", 
            "Non-GAAP Adjusted Net Income (reconciled)", "Adjusted US GAAP Net Income", 
            "Adjusted Ind AS Net Profit", "Ind AS Adjusted Net Income", "Adjusted Ind AS PAT", 
            "Adjusted IFRS Net Income", "Adjusted IFRS Profit for the period", 
            "Pro-forma Ind AS Net Profit", "Ind AS Pro-forma Net Income", "Adjusted US GAAP Net Profit", 
            "Reconciled GAAP Net Income"
        ],
        "reject": [
            "Non-GAAP metrics (unreconciled)", "Non-GAAP Earnings (without reconciliation table)", 
            "Plain Adjusted Earnings (no GAAP anchor)", "Adjusted PAT (unreconciled highlight)", 
            "GAAP One-time Adjustment", "Ind AS transition adjustment", "IFRS reconciliation impact", 
            "Statutory Ind AS Net Profit", "Reported US GAAP Net Income", "Reported IFRS Net Income", 
            "GAAP Adjusted EBITDA", "Ind AS Adjusted EBITDA", "Segment GAAP Adjusted Net Income"
        ],
        "definition": (
            "The final post-reconciliation adjusted bottom-line profit figure (`Adjusted Ind AS Net Profit / Adjusted US GAAP Net Income / Adjusted IFRS Net Income`) presented inside a formal statutory GAAP / Non-GAAP / Ind AS / IFRS reconciliation schedule, clearly bridging statutory reported profit to adjusted pro-forma profit.\n"
            "DISCRIMINATOR RULES:\n"
            "- VALUE TYPE: Absolute Currency post-reconciliation total figure (`a complete bottom-line net income figure — NEVER an individual adjustment delta, NEVER operating-level EBITDA`).\n"
            "- BASIS: GAAP / Ind AS / IFRS anchored — explicitly presented as 'Adjusted Ind AS Net Profit' / 'Adjusted US GAAP Net Income' / 'GAAP Pro-forma' inside a formal reconciliation schedule.\n"
            "- NEVER MAP TO THIS BUCKET: Unreconciled figures; plain 'Adjusted Earnings' / 'Adjusted EBITDA' without a GAAP/Ind AS-anchor reconciliation table; the individual line-item adjustment delta (`→ GAAP One-time Adjustment`); raw statutory starting net profit (`Reported Ind AS / US GAAP Net Income`)."
        ),
        "layer2_rules": (
            "MANDATORY STEP-BY-STEP RECONCILIATION BRIDGE & SCOPE VERIFICATION:\n"
            "1. STEP 1 (🚨 RECONCILIATION BRIDGE TABLE VERIFICATION - CRITICAL): ACTIVATE KNOWLEDGE of SEC Form 20-F / IFRS / Ind AS Transition Reconciliations. You are evaluating GAAP Adjusted. The candidate MUST originate from a formal reconciliation bridge table (`Reconciliation of Statutory Ind AS/IFRS Net Profit to Adjusted Non-GAAP Net Profit`). Inspect the table rows:\n"
            "   - DO NOT grab the top starting row (`Statutory Reported Ind AS / US GAAP Net Income`)!\n"
            "   - DO NOT grab the middle adjustment rows (`e.g., Stock-based compensation +Rs 200 Cr`). Those individual adjustment amounts belong strictly to **GAAP One-time Adjustment**!\n"
            "   - You MUST select the **final ending row** of the reconciliation bridge (`Adjusted Ind AS Net Profit / Non-GAAP Adjusted Net Income reconciled to GAAP / Pro-forma IFRS Net Income`).\n"
            "2. STEP 2 (STATUTORY ANCHOR PROOF): Confirm that the label explicitly anchors to GAAP, Ind AS, or IFRS. Reject plain 'Adjusted Net Profit' from narrative PR callouts lacking a reconciliation schedule.\n"
            "3. STEP 3 (BOTTOM-LINE PAT PROOF): Confirm the post-reconciliation figure is at the Net Income / PAT level after tax. Reject post-reconciliation 'GAAP Adjusted EBITDA' or 'Ind AS Adjusted Operating Profit'.\n"
            "4. STEP 4 (DUAL-SCOPE ENFORCEMENT): For Consolidated scope, select group-level Adjusted Ind AS / US GAAP Net Income from the Consolidated reconciliation schedule. Strictly reject Standalone parent reconciliation totals."
        ),
    },
    {
        "name": "EBIT",
        "type": "Currency",
        "accept": ["EBIT", "PBIT", "Operating Profit"],
        "reject": ["EBITDA", "PBITDA", "PBT", "Profit before tax", "Segment Result", "Adjusted EBIT", "Normalized EBIT", "Underlying EBIT", "EBIT before exceptional items", "EBIT Margin", "Operating Profit Margin", "before Depreciation", "Profit before Interest, Depreciation", "Profit before Finance Costs, Depreciation", "before tax", "Profit/(Loss) before exceptional and extraordinary items and tax"],
        "definition": (
            "Earnings Before Interest and Taxes (Operating Profit). Measures operational profitability after deducting operating expenses and Depreciation & Amortization, but before capital structure costs and taxation.\n"
            "DISCRIMINATOR RULES:\n"
            "- VALUE TYPE: Absolute Currency (NEVER a percentage).\n"
            "- BASIS: Reported/Statutory — the raw EBIT figure. The printed label MUST NOT carry qualifiers ('Adjusted' / 'Normalized' / 'Underlying' / 'Pro-forma').\n"
            "- LABEL / COMPONENT REQUIREMENT: The value must correspond to earnings AFTER Depreciation & Amortization are subtracted, but BEFORE Interest and Taxes are subtracted. If Depreciation/Amortization has not yet been subtracted (e.g. EBITDA), it is NOT EBIT and must be rejected.\n"
            "- NEVER MAP TO THIS BUCKET: EBITDA (the 'D' and 'A' matter — do NOT cross-map; Depreciation & Amortization MUST be subtracted to get EBIT); Adjusted/Normalized/Underlying EBIT (→ Adjusted EBIT); EBIT Margin (percentage, separate bucket); PBT / Profit before tax (different point in the P&L); Segment Result (segment-level, out of scope per the SEGMENT-QUALIFIED LABELS rule)."
        ),
        "layer2_rules": (
            "MANDATORY 3-STEP ACCOUNTING DECOMPOSITION & VERIFICATION:\n"
            "1. STEP 1 (🚨 DEPRECIATION EXCLUSION CHECK - CRITICAL): Did the company subtract Depreciation and Amortization? Look at the label carefully! If the label literally says 'before Depreciation' or 'before... Depreciation' (such as 'Profit before Interest, Depreciation' or 'Profit before Finance Costs, Depreciation'), STOP IMMEDIATELY! That is EBITDA, NOT EBIT! In EBIT, Depreciation MUST ALREADY BE SUBTRACTED!\n"
            "2. STEP 2 (🚨 INTEREST & TAX CHECK - CRITICAL): Confirm that Interest (Finance Costs) has NOT been subtracted! If the label says 'before tax' or 'Profit before tax' (such as 'Profit/(Loss) before exceptional items and tax' or 'Profit before tax' from an AUDITED_TABLE), Interest has ALREADY been subtracted! That represents PBT/EBT, NOT EBIT! You MUST STRICTLY REJECT IT!\n"
            "3. STEP 3 (ENTITY SCOPE CHECK): Ensure this represents whole-company operating earnings and NOT a segment profit result from Note on Segment Reporting (Note 38/54)!"
        ),
    },
    {
        "name": "EBITDA",
        "type": "Currency",
        "accept": ["EBITDA", "PBITDA", "Operating EBITDA", "Profit before Interest, Depreciation and Exceptional Items", "Profit before Finance Costs, Depreciation and Exceptional Items", "Profit before Depreciation, Interest and Tax"],
        "reject": ["EBIT", "PBIT", "Cash Profit", "PAT", "Adjusted EBITDA", "Normalized EBITDA", "Pro-forma EBITDA", "Underlying EBITDA", "EBITDA Margin", "Segment EBITDA", "Segment Result"],
        "definition": (
            "Earnings Before Interest, Taxes, Depreciation, and Amortization. A proxy for operational cash flow before capital reinvestment.\n"
            "DISCRIMINATOR RULES:\n"
            "- VALUE TYPE: Absolute Currency (NEVER a percentage).\n"
            "- BASIS: Reported/Statutory — the raw EBITDA figure. The printed label MUST NOT carry an 'Adjusted' / 'Normalized' / 'Pro-forma' / 'Underlying' qualifier (those route to Adjusted EBITDA).\n"
            "- LABEL / COMPONENT REQUIREMENT: Prefer direct labels ('EBITDA', 'PBITDA', 'Operating EBITDA') OR descriptive statutory tables ('Profit before Depreciation, Interest and Tax' / 'Profit before Finance Costs, Depreciation and Exceptional Items'). The value must correspond to earnings with D+A (and I+T) not yet subtracted.\n"
            "- NEVER MAP TO THIS BUCKET: EBIT (Depreciation & Amortization are NOT subtracted in EBITDA — letters matter); Adjusted/Normalized/Pro-forma EBITDA (→ Adjusted EBITDA); EBITDA Margin (percentage, separate bucket); Cash Profit / PAT; segment-level EBITDA; Segment Result."
        ),
        "layer2_rules": (
            "MANDATORY 4-STEP ACCOUNTING DECOMPOSITION & VERIFICATION:\n"
            "Do not just look at face-value acronyms! You MUST evaluate the candidate by checking these 4 accounting components step-by-step:\n"
            "1. STEP 1 (TAX EXCLUSION CHECK): Is this figure before Income Tax (PBT)? It MUST be before tax!\n"
            "2. STEP 2 (INTEREST EXCLUSION CHECK): Have financing costs / interest expenses been excluded or added back? (Look for phrases like 'before Interest' or 'before Finance Costs').\n"
            "3. STEP 3 (DEPRECIATION & AMORTIZATION CHECK): Does the company own depreciable physical assets? Have Depreciation and Amortization been explicitly excluded or added back? (Look for 'before Depreciation' or 'before D&A').\n"
            "4. STEP 4 (PROOF OF EXCLUSIONS BAN RULE): You MUST examine table structure. If a line item is located BELOW or AFTER Depreciation/Amortization or Interest on a P&L Statement (e.g., 'Profit / (loss) before exceptional items and tax' or 'Profit before tax' from an AUDITED_TABLE), Depreciation and Interest have ALREADY been subtracted! That represents PBT/EBT, NOT EBITDA, and must be STRICTLY REJECTED!"
        ),
    },
    {
        "name": "Adjusted EBIT",
        "type": "Currency",
        "accept": [
            "Adjusted EBIT", "Normalized EBIT", "Underlying EBIT", "EBIT before exceptional items", 
            "Pro-forma EBIT", "Adjusted Operating EBIT", "Adjusted PBIT", "Adjusted Profit before interest and tax", 
            "Adjusted Operating Profit", "Normalized PBIT", "Underlying PBIT", "Operating Profit before exceptional items", 
            "PBIT before exceptional items", "Profit before finance costs, tax and exceptional items", 
            "Adjusted Operating Income"
        ],
        "reject": [
            "Reported EBIT", "plain EBIT", "PBIT (plain)", "EBITDA", "Adjusted EBITDA", "Adjusted EBIT Margin", 
            "Adjusted Operating Profit Margin", "Adjusted PBIT Margin", "Segment EBIT", "before Depreciation", 
            "Profit before Interest, Depreciation", "Profit before Finance Costs, Depreciation", "before tax", 
            "Profit before tax", "PBT", "before exceptional and extraordinary items and tax", 
            "Profit/(loss) before exceptional items and tax", "Profit before exceptional items and tax", "Segment Adjusted EBIT"
        ],
        "definition": (
            "EBIT (`Operating Profit / PBIT`) explicitly adjusted for non-recurring operational items, restructuring charges, or one-off exceptional items to show 'clean' operating performance.\n"
            "DISCRIMINATOR RULES:\n"
            "- VALUE TYPE: Absolute Currency at the operating level (NEVER a percentage / margin, NEVER pre-tax PBT, NEVER post-tax PAT).\n"
            "- BASIS: Adjusted/Normalized — the printed label MUST contain 'Adjusted' / 'Normalized' / 'Underlying' alongside EBIT / PBIT / Operating Profit, OR represent statutory `Profit before finance costs, tax and exceptional items`.\n"
            "- NEVER MAP TO THIS BUCKET: plain/Reported EBIT (`→ EBIT`); EBITDA / Adjusted EBITDA (`the letter 'D' matters — Depreciation MUST be subtracted in EBIT`); Adjusted EBIT Margin; statutory PBT line `'Profit before exceptional items and tax'` (`Schedule III trap — Interest is already subtracted`); Segment Adjusted EBIT."
        ),
        "layer2_rules": (
            "MANDATORY STEP-BY-STEP ACCOUNTING & DEPRECIATION/INTEREST FIREWALL:\n"
            "1. STEP 1 (🚨 DEPRECIATION EXCLUSION FIREWALL - CRITICAL): You MUST check if Depreciation and Amortization have been subtracted! If the candidate label literally says 'before Depreciation', 'before D&A', or 'Profit before finance costs, depreciation and exceptional items', Depreciation has NOT been subtracted! That represents EBITDA / Adjusted EBITDA, NEVER Adjusted EBIT (`PBIT`). STRICTLY REJECT IT!\n"
            "2. STEP 2 (🚨 SCHEDULE III INTEREST TRAP FIREWALL - CRITICAL): ACTIVATE KNOWLEDGE of Indian Companies Act Schedule III (Division II Ind AS P&L structure). You MUST check if Finance Costs (`Interest`) have been subtracted! In an audited Schedule III P&L Statement, the line item titled `'Profit / (loss) before exceptional items and tax'` (`or 'Profit before tax'`) appears AFTER Finance Costs have already been deducted! That represents PBT / EBT before exceptional items, NEVER Adjusted EBIT! For a candidate to be Adjusted EBIT (`Adjusted PBIT`), it MUST explicitly state `'before finance costs'` (`e.g., 'Profit before finance costs, tax and exceptional items'`) OR verify that Finance Costs have NOT been deducted yet. STRICTLY REJECT line items where Interest has been deducted!\n"
            "3. STEP 3 (EXCEPTIONAL ADJUSTMENT PROOF): Confirm the figure explicitly removes/adjusts operational one-off exceptional items (`Note 33/34`). Do not grab plain unadjusted EBIT or PBIT.\n"
            "4. STEP 4 (MATHEMATICAL IDENTITY CHECK): Confirm that Adjusted EBIT is numerically lower than Adjusted EBITDA by the statutory depreciation amount ($Adjusted EBIT < Adjusted EBITDA$).\n"
            "5. STEP 5 (DUAL-SCOPE ENFORCEMENT): For Consolidated scope, select group-level Adjusted PBIT. Strictly reject Note 38/54 Segment Adjusted EBIT."
        ),
    },
    {
        "name": "Adjusted EBITDA",
        "type": "Currency",
        "accept": ["Adjusted EBITDA", "Normalized EBITDA", "Pro-forma EBITDA", "Underlying EBITDA", "EBITDA before exceptional items", "Adjusted Operating EBITDA", "adjusted operating EBITDA", "Profit before Finance Costs, Depreciation and Exceptional Items", "Profit before Interest, Depreciation and Exceptional Items", "Profit before Depreciation, Interest and Tax (before exceptional items)"],
        "reject": ["Plain EBITDA", "Reported EBITDA", "PBITDA (plain)", "EBIT", "Adjusted EBIT", "Adjusted EBITDA Margin", "Normalized EBITDA Margin", "Cash Profit", "Segment EBITDA", "Segment Result"],
        "definition": (
            "EBITDA further refined to exclude items like restructuring costs, stock-based compensation, forex devaluations, or legal settlements to reflect true recurring operational cash generation.\n"
            "DISCRIMINATOR RULES:\n"
            "- VALUE TYPE: Absolute Currency (NEVER a percentage / margin).\n"
            "- BASIS: Adjusted/Normalized/Pro-forma — the printed label MUST literally contain one of these qualifiers alongside 'EBITDA' OR represent statutory profit before D&A and exceptional items.\n"
            "- NEVER MAP TO THIS BUCKET: plain/Reported EBITDA (→ EBITDA); EBIT or Adjusted EBIT (the 'D' and 'A' matter); EBITDA Margin / Adjusted EBITDA Margin; Cash Profit; segment-level EBITDA; Segment Result."
        ),
        "layer2_rules": (
            "MANDATORY STEP-BY-STEP VERIFICATION:\n"
            "1. STEP 1 (VERIFY BASE EBITDA COMPONENTS): First, confirm that Interest, Taxes, and Depreciation & Amortization are ALL excluded! (Must be before Interest, Tax, and Depreciation).\n"
            "2. STEP 2 (VERIFY EXCEPTIONAL / ONE-TIME ADJUSTMENT): Check whether the figure explicitly adjusts for or excludes statutory Exceptional Items (e.g., Note 33/34 forex losses, impairment, restructuring).\n"
            "3. STEP 3 (ACCEPT STATUTORY & DESCRIPTIVE LABELS): Accept both acronym labels ('Adjusted EBITDA', 'Adjusted Operating EBITDA', 'Normalized EBITDA') AND descriptive statutory Indian GAAP labels ('Profit before Finance Costs, Depreciation and Exceptional Items' / 'Profit before Interest, Depreciation & Exceptional Items'). Do not return 0 candidates if these phrases exist!\n"
            "4. STEP 4 (PROOF OF EXCLUSIONS BAN RULE): Do NOT select Consolidated PBT or EBT just because it says 'before exceptional items'. The item MUST be before Depreciation and Interest! Rejects statutory P&L lines titled 'Profit/(loss) before exceptional items and tax' or 'Profit before tax' from an AUDITED_TABLE."
        ),
    },
    {
        "name": "Core Operating Profit",
        "type": "Currency",
        "accept": [
            "Core Operating Profit", "Underlying Operating Profit", "Core Operating Earnings", 
            "Core PBIT", "Core EBIT", "Underlying PBIT", "Underlying EBIT", 
            "Operating Profit from core operations", "Operating profit ex-other operating income", 
            "Core PPOP", "Core Operating Profit before provisions", "Operating Profit before provisions excluding treasury gains"
        ],
        "reject": [
            "Segment Result", "Operating Profit (plain)", "EBIT", "EBITDA", "Adjusted EBIT", 
            "Core Earnings", "Core PAT", "Core Net Income", "Underlying PAT", "Core EBITDA", 
            "Core Operating EBITDA", "Core Margin", "Base Business Margin", "Core Operating Margin", 
            "PPOP (if treasury included)", "Segment Core Operating Profit"
        ],
        "definition": (
            "Profit strictly from primary operating activities (`Core PBIT / Core EBIT`), excluding both group corporate adjustments/non-operating treasury gains and non-core secondary business units.\n"
            "DISCRIMINATOR RULES:\n"
            "- VALUE TYPE: Absolute Currency at the operating-profit level (`after D&A, but before Interest and Tax` — NEVER a margin percentage, NEVER bottom-line PAT).\n"
            "- BASIS: Core/Underlying — the printed label MUST literally contain 'Core Operating' / 'Underlying Operating' / 'Core PBIT' / 'Core EBIT', OR represent operating profit explicitly adjusted to exclude non-operating treasury/other income (`Core PPOP in banks`).\n"
            "- NEVER MAP TO THIS BUCKET: plain Operating Profit (`→ EBIT`); EBITDA / Core EBITDA (`before D&A`); Adjusted EBIT (`different qualifier semantics`); 'Core Earnings / Core PAT' (`→ bottom-line post-tax, separate bucket`); Segment Result (`Note 38 out of scope`); Core Margin."
        ),
        "layer2_rules": (
            "MANDATORY STEP-BY-STEP ACCOUNTING & SCOPE VERIFICATION:\n"
            "1. STEP 1 (🚨 OPERATING LEVEL VS. BOTTOM-LINE PAT FIREWALL - CRITICAL): You are evaluating Core Operating Profit (`Core EBIT / Core PBIT`). Confirm that Depreciation & Amortization HAVE been subtracted, but Finance Costs (`Interest`) and Income Tax HAVE NOT been subtracted! If the candidate is post-tax (`Core PAT / Core Earnings`) or pre-D&A (`Core EBITDA`), STRICTLY REJECT IT!\n"
            "2. STEP 2 (EXCLUSION OF NON-OPERATING & TREASURY INCOME): ACTIVATE KNOWLEDGE of RBI Master Directions for Banks/NBFCs and Schedule III Note 26/29. Confirm that the figure excludes non-operating income (`Note 26/29 Other Income`), one-off capital gains, and investment income. For BANKS & NBFCs (`HDFC Bank, ICICI Bank`), Core Operating Profit is defined as **PPOP excluding Treasury Income** (`Core PPOP`). If the candidate is raw PPOP that includes treasury trading gains, strictly reject it unless treasury gains are excluded!\n"
            "3. STEP 3 (DUAL-SCOPE ENFORCEMENT): For Consolidated scope, select group-level Core Operating Profit. Strictly reject Note 38/54 Segment Results (`e.g., Retail Banking segment operating profit`)."
        ),
    },
    {
        "name": "EBIT Margin",
        "type": "Percentage",
        "accept": ["EBIT Margin", "EBIT Margin %", "Operating Profit Margin", "Operating Profit Margin %", "Operating Margin", "PBIT Margin"],
        "reject": ["EBITDA Margin", "Net Profit Margin", "Gross Margin", "Adjusted EBIT Margin", "Normalized EBIT Margin", "Underlying EBIT Margin", "EBIT", "Adjusted EBIT", "Segment EBIT Margin", "before Depreciation"],
        "definition": (
            "EBIT expressed as a percentage of total revenue. Measures operational efficiency after asset wear-and-tear.\n"
            "DISCRIMINATOR RULES:\n"
            "- VALUE TYPE: Percentage / Margin Ratio (always 'x.x%' alongside the word 'Margin'). NEVER an absolute currency amount.\n"
            "- BASIS: Reported/Statutory — the raw EBIT margin. The printed label MUST NOT carry 'Adjusted' / 'Normalized' / 'Pro-forma' / 'Underlying' qualifiers.\n"
            "- NEVER MAP TO THIS BUCKET: EBITDA Margin (letter 'D' matters); Net Profit Margin / Gross Margin (different aggregates); absolute EBIT figures (→ EBIT) or Adjusted EBIT (→ Adjusted EBIT); 'Adjusted EBIT Margin' (forbidden qualifier-strip)."
        ),
        "layer2_rules": (
            "MANDATORY 3-STEP ACCOUNTING DECOMPOSITION & VERIFICATION:\n"
            "1. STEP 1 (VERBATIM & FORMULA CHECK): If a candidate is labeled 'Operating Profit Margin' or 'PBIT Margin', you MUST examine the narrative or table structure. If the text defines this margin as being BEFORE Depreciation & Amortization (i.e., EBITDA / PBITDA margin), it is NOT EBIT Margin! You MUST STRICTLY REJECT IT!\n"
            "2. STEP 2 (MATHEMATICAL IDENTITY CHECK): In any company with Depreciation & Amortization, statutory EBIT Margin MUST be numerically lower than EBITDA Margin ($EBIT Margin < EBITDA Margin$). If the percentage is gross of depreciation, reject it.\n"
            "3. STEP 3 (SCOPE PRUNING): Strictly reject segment-level EBIT margins (e.g., pipe segment margin) or division-specific operating margins."
        ),
    },
    {
        "name": "EBITDA Margin",
        "type": "Percentage",
        "accept": ["EBITDA Margin", "EBITDA Margin %", "PBITDA Margin", "Operating EBITDA Margin", "Operating Profit Margin (if before D&A)"],
        "reject": ["EBIT Margin", "Net Profit Margin", "Gross Margin", "Adjusted EBITDA Margin", "Normalized EBITDA Margin", "Pro-forma EBITDA Margin", "Underlying EBITDA Margin", "EBITDA", "Adjusted EBITDA", "Segment EBITDA Margin"],
        "definition": (
            "EBITDA as a percentage of revenue. Used to compare operational cash generating efficiency across companies.\n"
            "DISCRIMINATOR RULES:\n"
            "- VALUE TYPE: Percentage / Margin Ratio (always 'x.x%' alongside the word 'Margin'). NEVER an absolute currency amount.\n"
            "- BASIS: Reported/Statutory — the raw EBITDA margin. The printed label MUST NOT carry 'Adjusted' / 'Normalized' / 'Pro-forma' / 'Underlying' qualifiers.\n"
            "- NEVER MAP TO THIS BUCKET: EBIT Margin ('D' and 'A' matter); Net Profit Margin / Gross Margin (different aggregates); absolute EBITDA figures (→ EBITDA) or Adjusted EBITDA (→ Adjusted EBITDA); 'Adjusted/Normalized/Pro-forma EBITDA Margin' (forbidden qualifier-strip)."
        ),
        "layer2_rules": (
            "MANDATORY 3-STEP ACCOUNTING DECOMPOSITION & VERIFICATION:\n"
            "1. STEP 1 (TERMINOLOGY & SYNONYM CHECK): In corporate MD&A narratives, management often refers to EBITDA Margin loosely as 'Operating Profit Margin' or 'PBITDA Margin'. You may accept 'Operating Profit Margin' as EBITDA Margin ONLY IF the surrounding text or table confirms it is calculated BEFORE Depreciation and Amortization!\n"
            "2. STEP 2 (VERBATIM EXCLUSION PROOF): If the candidate represents a margin calculated AFTER subtracting Depreciation & Amortization (which is EBIT Margin), you MUST STRICTLY REJECT IT!\n"
            "3. STEP 3 (SCOPE PRUNING): Strictly reject segment-level EBITDA margins or subsidiary-only margins."
        ),
    },
    {
        "name": "Base Business Margin",
        "type": "Percentage",
        "accept": [
            "Base Business Margin", "Core Margin", "Base Margin", "Core Business Margin", 
            "Margin of base business", "Legacy business margin", "Core operations margin"
        ],
        "reject": [
            "Gross Margin", "EBITDA Margin", "EBIT Margin", "Operating Margin", "Net Margin", 
            "Net Profit Margin", "Core Earnings", "Core Operating Profit", "Segment Margin (unless specifically legacy core)", 
            "Consolidated Margin", "Group Margin"
        ],
        "definition": (
            "Profit margin specifically for the legacy or core business units of a company, intentionally excluding new acquisitions, digital incubations, or hyper-growth non-core segments.\n"
            "DISCRIMINATOR RULES:\n"
            "- VALUE TYPE: Percentage / Margin Ratio (NEVER absolute currency).\n"
            "- BASIS: Reported margin specifically tracking the core/legacy/base business — distinct from the overall blended group-level margin.\n"
            "- NEVER MAP TO THIS BUCKET: Overall Group EBITDA Margin / EBIT Margin (`those blend base + new segments`); absolute currency Core Earnings; generic segment margins."
        ),
        "layer2_rules": (
            "MANDATORY STEP-BY-STEP SCOPE & SEGMENT EXEMPTION VERIFICATION:\n"
            "1. STEP 1 (🚨 IND AS 108 SEGMENT REPORTING EXEMPTION - CRITICAL): ACTIVATE KNOWLEDGE of Ind AS 108 Operating Segments. Unlike group-level metrics (`like EBITDA Margin`) where Note 108 Segment Reporting is BANNED, Base Business Margin explicitly measures mature/legacy segments! Therefore, you ARE EXPLICITLY ALLOWED to select candidates from Note 108 Segment Reporting IF AND ONLY IF the segment represents the Base/Core/Established Business of the company (`e.g., ITC Cigarettes, Airtel India Mobile Services`).\n"
            "2. STEP 2 (DIFFERENTIATION FROM GROUP TOTALS): Do not simply grab the Consolidated Group Operating Margin. The candidate MUST explicitly refer to the margin of the 'Base Business', 'Core Business', or a specific mature legacy operation that management isolates from new ventures.\n"
            "3. STEP 3 (VALUE TYPE): Must be a percentage (`%`) margin, never an absolute currency figure."
        ),
    },
    {
        "name": "Adjusted ROE",
        "type": "Percentage",
        "accept": [
            "Adjusted ROE", "Adjusted Return on Equity", "Normalized ROE", "Underlying ROE", 
            "Core ROE", "ROE (Adjusted)", "Return on Equity (Normalized)", "ROE before exceptional items", 
            "Adjusted ROAE", "Adjusted Return on Average Equity"
        ],
        "reject": [
            "Reported ROE", "plain ROE", "ROCE", "ROIC", "RONA", "Adjusted ROA", "Return on Equity (no qualifier)", 
            "Net Income", "Total Equity", "Average Equity", "Core ROA"
        ],
        "definition": (
            "Return on Equity mathematically calculated using adjusted/normalized net income in the numerator, demonstrating the true recurring return generated on shareholders' equity.\n"
            "DISCRIMINATOR RULES:\n"
            "- VALUE TYPE: Percentage / Return Ratio (NEVER absolute currency).\n"
            "- BASIS: Adjusted/Normalized — the printed label MUST contain 'Adjusted' / 'Normalized' / 'Underlying' / 'Core' alongside ROE / Return on Equity.\n"
            "- NEVER MAP TO THIS BUCKET: plain/Reported ROE (`no dedicated bucket — route to null`); ROCE / ROIC (`denominator includes debt`); Adjusted ROA (`denominator is total assets`); absolute currency inputs (`Net Income, Equity`)."
        ),
        "layer2_rules": (
            "MANDATORY STEP-BY-STEP ACCOUNTING & RATIO VERIFICATION:\n"
            "1. STEP 1 (🚨 NUMERATOR ADJUSTMENT PROOF - CRITICAL): ACTIVATE KNOWLEDGE of Ratio Analysis. You are evaluating Adjusted ROE. The candidate MUST explicitly be a return ratio where the numerator (`PAT`) has been adjusted for one-time/exceptional items (`e.g., 'ROE using Normalized PAT'`). Do NOT grab statutory unadjusted ROE from the 'Key Financial Ratios' table (Note 40) unless it explicitly carries an 'Adjusted' or 'Normalized' qualifier!\n"
            "2. STEP 2 (DENOMINATOR VERIFICATION): Confirm the denominator is Equity (`Net Worth / Shareholders' Equity`). Reject ROCE (`Return on Capital Employed` - denominator includes debt) and Adjusted ROA (`denominator is Total Assets`).\n"
            "3. STEP 3 (DUAL-SCOPE & BANKING ASYMMETRY ENFORCEMENT): ACTIVATE KNOWLEDGE of RBI Banking Consolidation. In large bank conglomerates (`e.g., SBI, ICICI`), Standalone banking ROE is structurally higher than Consolidated Group ROE. If evaluating Consolidated scope, you MUST verify the table header says 'Consolidated'. Do NOT grab the Standalone commercial banking ROE from the Directors' Report summary!"
        ),
    },
    {
        "name": "Adjusted ROA",
        "type": "Percentage",
        "accept": [
            "Adjusted ROA", "Adjusted Return on Assets", "Normalized ROA", "Underlying ROA", 
            "Core ROA", "ROA (Adjusted)", "Return on Assets (Normalized)", "ROA before exceptional items", 
            "Adjusted ROAA", "Adjusted Return on Average Assets"
        ],
        "reject": [
            "Reported ROA", "plain ROA", "RONA", "ROE", "Adjusted ROE", "ROCE", "ROIC", 
            "Return on Assets (no qualifier)", "Net Income", "Total Assets", "Average Assets"
        ],
        "definition": (
            "Return on Assets mathematically calculated using adjusted/normalized net income in the numerator, providing a clean measure of asset utilization efficiency without the noise of one-off charges.\n"
            "DISCRIMINATOR RULES:\n"
            "- VALUE TYPE: Percentage / Return Ratio (NEVER absolute currency).\n"
            "- BASIS: Adjusted/Normalized — the printed label MUST contain 'Adjusted' / 'Normalized' / 'Underlying' / 'Core' alongside ROA / Return on Assets.\n"
            "- NEVER MAP TO THIS BUCKET: plain/Reported ROA (`statutory unadjusted`); Adjusted ROE / ROCE (`different denominators`); absolute currency inputs (`Net Income, Average Assets`)."
        ),
        "layer2_rules": (
            "MANDATORY STEP-BY-STEP ACCOUNTING & RATIO VERIFICATION:\n"
            "1. STEP 1 (🚨 NUMERATOR ADJUSTMENT PROOF - CRITICAL): ACTIVATE KNOWLEDGE of Ratio Analysis. You are evaluating Adjusted ROA. The candidate MUST explicitly be a return ratio where the numerator (`PAT`) has been adjusted for exceptional items. Do NOT grab statutory unadjusted ROA from the 'Key Financial Ratios' table!\n"
            "2. STEP 2 (DENOMINATOR VERIFICATION): Confirm the denominator is Assets (`Total Assets / Average Assets`). Reject Adjusted ROE (`denominator is Equity`).\n"
            "3. STEP 3 (INPUT REJECTION): Do NOT grab the absolute currency denominator `'Average Total Assets'` just because it appears in a table calculating ROA.\n"
            "4. STEP 4 (DUAL-SCOPE & BANKING ASYMMETRY ENFORCEMENT): ACTIVATE KNOWLEDGE of RBI Banking Consolidation. In large bank conglomerates, Standalone commercial banking ROA (`~1.8%`) is completely different from Consolidated Group ROA (`~1.3%`). You MUST rigorously check the table header/chapter (`Standalone vs Consolidated`) to prevent cross-contamination!"
        ),
    },
    {
        "name": "Free Cash Flow (FCF)",
        "type": "Currency",
        "accept": [
            "Free Cash Flow", "FCF", "Free Cash Flow (FCF)", "Free cash flow generation", 
            "Operating Free Cash Flow", "FCF before dividends", "Unlevered Free Cash Flow", 
            "Levered Free Cash Flow"
        ],
        "reject": [
            "CFO", "Cash from Operations", "Operating Cash Flow", "Net cash generated from operating activities", 
            "FCFE", "FCFF", "Funds From Operations", "FFO", "Distributable Cash Flow", "Cash from Investing", 
            "Cash from Financing", "EBITDA minus Capex", "Cash Profit"
        ],
        "definition": (
            "The pure cash generated by the business after deducting capital expenditures (`CapEx`) required to maintain or expand its asset base. It represents the cash truly free for debt reduction or shareholder distribution.\n"
            "DISCRIMINATOR RULES:\n"
            "- VALUE TYPE: Absolute Currency (a cash-flow figure).\n"
            "- BASIS: The specific 'Free Cash Flow' / 'FCF' label — NEVER a generic 'cash' line and NEVER statutory gross CFO.\n"
            "- NEVER MAP TO THIS BUCKET: Net cash generated from operating activities / CFO (`Ind AS 7 statutory gross cash flow BEFORE CapEx`); Funds From Operations / FFO (`REIT metric`); Distributable Cash Flow (`MLP/REIT metric`); synthetic approximations like `EBITDA - Capex`."
        ),
        "layer2_rules": (
            "MANDATORY STEP-BY-STEP ACCOUNTING & MATHEMATICAL VERIFICATION:\n"
            "1. STEP 1 (🚨 THE CFO VS. FCF FIREWALL - CRITICAL): ACTIVATE KNOWLEDGE of Ind AS 7 Statement of Cash Flows. In India, companies report 'Net cash generated from operating activities' (`CFO`). CFO is strictly BEFORE Capital Expenditures (`CapEx`). Free Cash Flow (FCF) is mathematically defined as CFO MINUS CapEx. If a candidate is simply the raw CFO figure from the Cash Flow Statement, you MUST STRICTLY REJECT IT, even if it appears under a PR heading titled 'Free Cash Flow Generation'!\n"
            "2. STEP 2 (MATHEMATICAL IDENTITY PROOF): Verify the formula: `FCF = CFO - CapEx`. The FCF candidate MUST be numerically lower than statutory CFO (assuming normal positive CapEx).\n"
            "3. STEP 3 (EBITDA PROXY EXCLUSION): Strictly reject synthetic analyst approximations like 'EBITDA minus Capex'. FCF must be derived from actual operating cash flow (post working-capital changes and taxes)."
        ),
    },
    {
        "name": "Funds From Operations (FFO)",
        "type": "Currency",
        "accept": [
            "Funds From Operations", "FFO", "Funds from Operations (FFO)", "NAREIT FFO"
        ],
        "reject": [
            "AFFO", "Adjusted FFO", "Free Cash Flow", "FCF", "Cash from Operations", "CFO", 
            "Net cash generated from operating activities", "Distributable Cash Flow", "Operating Cash Flow", 
            "NDCF", "Net Distributable Cash Flow"
        ],
        "definition": (
            "A sector-specific measure of cash generated by Real Estate Investment Trusts (`REITs`) or Infrastructure InvITs, calculated by adding depreciation and amortization to earnings and subtracting any gains on sales of property.\n"
            "DISCRIMINATOR RULES:\n"
            "- VALUE TYPE: Absolute Currency.\n"
            "- BASIS: The specific 'Funds From Operations' / 'FFO' label — strictly a REIT / InvIT / Real Estate sector metric.\n"
            "- NEVER MAP TO THIS BUCKET: Adjusted FFO / AFFO (`a downstream metric that deducts maintenance CapEx`); Free Cash Flow / FCF; statutory Operating Cash Flow / CFO (`Ind AS 7 metric - includes working capital changes which FFO excludes`); Net Distributable Cash Flow (`NDCF`)."
        ),
        "layer2_rules": (
            "MANDATORY STEP-BY-STEP ACCOUNTING VERIFICATION:\n"
            "1. STEP 1 (🚨 FFO VS. NDCF/CFO FIREWALL - CRITICAL): ACTIVATE KNOWLEDGE of SEBI REIT Regulations and NAREIT Guidelines. FFO is a specific non-GAAP earnings metric (`PAT + D&A - Property Gains`). Do NOT confuse FFO with 'Net Distributable Cash Flow' (`NDCF`)! Do NOT confuse FFO with statutory Ind AS 7 'Net cash generated from operating activities' (`CFO`). If the label is NDCF or CFO, STRICTLY REJECT IT!\n"
            "2. STEP 2 (AFFO EXCLUSION): Confirm the label is FFO, not AFFO (`Adjusted FFO`).\n"
            "3. STEP 3 (SECTOR RELEVANCE): If the company is a standard manufacturing or IT company (`e.g., Infosys, Tata Steel`), they do NOT report FFO. Return 0 candidates rather than forcing a CFO proxy."
        ),
    },
    {
        "name": "Distributable Cash Flow",
        "type": "Currency",
        "accept": ["Distributable Cash Flow", "Cash Available for Distribution", "CAD", "Distributable Surplus"],
        "reject": ["Free Cash Flow", "FCF", "plain Cash Flow", "Dividend Paid", "CFO", "Operating Cash Flow", "Funds From Operations", "FFO", "Distributable Reserves"],
        "definition": (
            "The actual cash available to be paid out as dividends after all necessary capital and debt obligations are met.\n"
            "DISCRIMINATOR RULES:\n"
            "- VALUE TYPE: Absolute Currency.\n"
            "- BASIS: A 'distributable' / 'cash available for distribution' label tied to dividend capacity (not the dividend actually paid).\n"
            "- NEVER MAP TO THIS BUCKET: Free Cash Flow / FCF (broader, pre-distribution — separate bucket); Funds From Operations / FFO (real-estate-specific, separate); generic Cash from Operations / CFO; the dividend actually paid (output, not capacity); 'Distributable Reserves' (an equity / reserves line on the balance sheet, not a cash flow)."
        ),
        "layer2_rules": (
            "ANOMALY PREVENTION RULE: In Indian GAAP / Ind AS, manufacturing companies do not report Distributable Cash Flow (an MLP/REIT metric). NEVER select 'Total amount available for appropriation' or 'Retained earnings carried forward' from the Directors' Report! If no explicit Distributable Cash Flow exists, return null / 0 candidates."
        ),
    },
    {
        "name": "Net Debt",
        "type": "Currency",
        "accept": ["Net Debt", "Net Borrowings", "Net Financial Debt", "Net Indebtedness"],
        "reject": ["Gross Debt", "Total Debt", "Total Borrowings", "Total Liabilities", "Long-term Borrowings", "Short-term Borrowings", "Net Cash Position", "Net Surplus Cash"],
        "definition": (
            "Total financial debt minus cash and cash equivalents. Shows the true leverage of the company.\n"
            "GEARING & NOTES GUIDANCE: For Consolidated Net Debt, always check the Gearing Ratio / Capital Risk Management disclosure notes (typically Note 39 or 40 in the Consolidated Financial Statements, showing a gearing table with Loans and borrowings less cash and cash equivalents).\n"
            "DISCRIMINATOR RULES:\n"
            "- VALUE TYPE: Absolute Currency (positive when the company is a net borrower; negative when net cash).\n"
            "- BASIS: The specific 'Net Debt' / 'Net Borrowings' label — the netting against cash has ALREADY been done by the issuer.\n"
            "- COMPANY DEFINITION SUPPORT: Many reports explicitly state the formula (example: 'Net Debt is interest-bearing loans and borrowings less cash and cash equivalents'). Use such definitions to locate the presented figure, but the printed label must still be a Net Debt variant.\n"
            "- NEVER MAP TO THIS BUCKET: Gross Debt / Total Debt / Total Borrowings / Total Liabilities (NOT netted against cash); standalone Long-term or Short-term Borrowings line items; Net Surplus Cash (→ separate bucket — the opposite-sign concept)."
        ),
    },
    {
        "name": "Net Surplus Cash",
        "type": "Currency",
        "accept": ["Net Surplus Cash", "Net Cash Balance", "Net Cash Position", "Net Cash Surplus"],
        "reject": ["Gross Cash", "Cash & Cash Equivalents", "Cash Balance (gross)", "FCF", "Free Cash Flow", "Net Debt"],
        "definition": (
            "The excess cash remaining after all debt and immediate liabilities are theoretically settled.\n"
            "DISCRIMINATOR RULES:\n"
            "- VALUE TYPE: Absolute Currency (positive when company is net cash — cash exceeds debt).\n"
            "- BASIS: A 'Net Cash' / 'Net Surplus Cash' label — the netting against debt has ALREADY been done by the issuer.\n"
            "- NEVER MAP TO THIS BUCKET: gross Cash & Cash Equivalents (NOT netted against debt); Free Cash Flow (a flow, not a stock); Net Debt (→ separate bucket — the opposite-sign concept)."
        ),
    },
    {
        "name": "Constant Currency Revenue",
        "type": "Currency",
        "accept": [
            "Constant Currency Revenue", "CC Revenue", "FX-neutral Revenue", "Revenue in constant currency terms"
        ],
        "reject": [
            "Reported Revenue", "Total Revenue", "plain Revenue", "Adjusted Revenue", "Constant Currency Revenue Growth", 
            "CC Revenue Growth %", "Organic Revenue"
        ],
        "definition": (
            "A non-GAAP revenue metric calculated by translating current period foreign-currency revenues using the exchange rates of the prior comparable period. It demonstrates pure business volume growth by eliminating the artificial inflation/deflation caused by FX rate fluctuations.\n"
            "DISCRIMINATOR RULES:\n"
            "- VALUE TYPE: Absolute Currency (a revenue figure — NEVER a percentage growth rate).\n"
            "- BASIS: Constant-Currency / FX-neutral — the printed label MUST explicitly contain 'Constant Currency' / 'CC' / 'FX-neutral' / 'Fixed Exchange Rate' alongside Revenue.\n"
            "- NEVER MAP TO THIS BUCKET: Reported / Total / plain Revenue (`statutory — completely separate`); Adjusted Revenue (`usually excludes acquisitions, not FX`); Constant Currency Revenue Growth (`the percentage bucket, NOT this absolute currency bucket`)."
        ),
        "layer2_rules": (
            "MANDATORY STEP-BY-STEP FX ADJUSTMENT VERIFICATION:\n"
            "1. STEP 1 (🚨 THE PERCENTAGE VS. CURRENCY FIREWALL - CRITICAL): ACTIVATE KNOWLEDGE of IT Services Reporting (`e.g., Infosys, TCS`). Companies frequently report Constant Currency Revenue Growth (`e.g., '12.5% YoY'`). You are evaluating the absolute currency bucket. If the candidate is a percentage (`%`), STRICTLY REJECT IT!\n"
            "2. STEP 2 (FX EXPLICIT QUALIFIER CHECK): The table header or text MUST explicitly state 'Constant Currency' or 'FX-neutral'. Do NOT grab statutory consolidated revenue assuming it is CC revenue.\n"
            "3. STEP 3 (US DOLLAR VS LOCAL CURRENCY AWARENESS): In Indian IT, CC Revenue is often reported in USD millions, while statutory revenue is in INR Crores. Accept the CC Revenue figure regardless of the reporting currency (`USD/EUR/INR`) as long as it has the 'Constant Currency' qualifier."
        ),
    },
    {
        "name": "Constant Currency Revenue Growth",
        "type": "Percentage",
        "accept": ["Constant Currency Revenue Growth", "CC Revenue Growth", "FX-neutral Revenue Growth", "Revenue growth in constant currency"],
        "reject": ["Reported Revenue Growth", "Organic Growth", "Constant Currency Revenue", "CC Revenue", "Adjusted Revenue Growth", "Volume Growth"],
        "definition": (
            "The percentage increase in revenue adjusted for currency shifts to show underlying volume/price growth.\n"
            "DISCRIMINATOR RULES:\n"
            "- VALUE TYPE: Percentage / Growth Rate (displayed as 'x.x%' — NEVER an absolute currency figure).\n"
            "- BASIS: Constant-Currency / FX-neutral growth — the printed label MUST literally combine 'Constant Currency' / 'CC' with 'Growth' / 'Growth %'.\n"
            "- NEVER MAP TO THIS BUCKET: the absolute Constant Currency Revenue figure (→ separate bucket); reported revenue growth; Organic Growth; Adjusted Revenue Growth."
        ),
    },
    {
        "name": "Constant Currency Opex",
        "type": "Currency",
        "accept": [
            "Constant Currency Opex", "CC Opex", "FX-neutral Opex", "Operating Expenses in constant currency"
        ],
        "reject": [
            "Reported Opex", "Total Opex", "Opex Growth %", "Constant Currency Revenue", "Cost of Revenue (no FX qualifier)"
        ],
        "definition": (
            "Operating expenses translated using prior period exchange rates to isolate actual cost-management performance from currency volatility.\n"
            "DISCRIMINATOR RULES:\n"
            "- VALUE TYPE: Absolute Currency (an expense figure — NEVER a percentage).\n"
            "- BASIS: Constant-Currency / FX-neutral — the printed label MUST literally contain 'Constant Currency' / 'CC' / 'FX-neutral' alongside 'Opex' / 'Operating Expenses' / 'Costs'.\n"
            "- NEVER MAP TO THIS BUCKET: reported / total statutory Opex; percentage CC Opex growth; Constant Currency Revenue."
        ),
        "layer2_rules": (
            "MANDATORY STEP-BY-STEP FX ADJUSTMENT VERIFICATION:\n"
            "1. STEP 1 (🚨 THE PERCENTAGE VS. CURRENCY FIREWALL - CRITICAL): If the candidate is a percentage (`%`) representing cost growth, STRICTLY REJECT IT!\n"
            "2. STEP 2 (FX EXPLICIT QUALIFIER CHECK): The label MUST explicitly state 'Constant Currency' or 'FX-neutral'. Do NOT grab statutory operating expenses.\n"
            "3. STEP 3 (SCOPE VERIFICATION): Ensure it represents Operating Expenses (`Opex`), not Cost of Goods Sold (`COGS`) or Revenue."
        ),
    },
    {
        "name": "ARPU",
        "type": "Currency",
        "accept": [
            "ARPU", "Average Revenue Per User", "Average Revenue Per Subscriber", "Blended ARPU"
        ],
        "reject": [
            "ARPPU", "Average Revenue Per Paying User", "Revenue per unit", "Revenue per Employee", 
            "Total Revenue", "Subscriber count"
        ],
        "definition": (
            "Average Revenue Per User (or Subscriber). A key unit-economic metric for telecommunications (`e.g., Bharti Airtel, Jio`), streaming, or SaaS businesses, calculated by dividing total revenue by the total average user base.\n"
            "DISCRIMINATOR RULES:\n"
            "- VALUE TYPE: Per-User Currency (a small Rs/USD figure per user/subscriber per period — NEVER a total revenue figure in millions/billions).\n"
            "- BASIS: Sector-specific (Telecom / Media / SaaS).\n"
            "- NEVER MAP TO THIS BUCKET: ARPPU (`Average Revenue Per Paying User` — a stricter cohort that excludes free users); Revenue per Unit / Revenue per Employee; total aggregate revenue figures; raw subscriber counts."
        ),
        "layer2_rules": (
            "MANDATORY STEP-BY-STEP TELECOM METRIC VERIFICATION:\n"
            "1. STEP 1 (🚨 ARPPU VS. ARPU FIREWALL - CRITICAL): ACTIVATE KNOWLEDGE of SaaS/Media Unit Economics. ARPU (`Average Revenue Per User`) divides revenue by ALL users (`free + paid`). ARPPU (`Average Revenue Per Paying User`) divides revenue ONLY by paid users. If a company reports BOTH, you MUST NOT grab ARPPU and label it ARPU. Ensure the label specifically says ARPU.\n"
            "2. STEP 2 (MAGNITUDE CHECK): ARPU is a small per-unit currency figure (`e.g., Rs. 200 per month, $15 per month`). If the candidate is a massive aggregate figure (`e.g., 20,000 Crores`), it is Total Revenue. STRICTLY REJECT IT!\n"
            "3. STEP 3 (DENOMINATOR CHECK): Do NOT select raw subscriber counts (`e.g., '300 Million Subscribers'`) instead of the currency ARPU."
        ),
    },
    {
        "name": "Collections",
        "type": "Currency",
        "accept": [
            "Collections", "Sales Collections", "Cash Collections", "Customer Collections", "Collection Value"
        ],
        "reject": [
            "Revenue", "Revenue from Operations", "CFO", "Operating Cash Flow", "Receipts (generic)", 
            "Order Book", "Order Backlog", "Pre-sales", "Bookings"
        ],
        "definition": (
            "The actual cash received from customers during the period. In sectors like Real Estate (where Ind AS 115 revenue recognition is deferred until project completion) or lending, Collections provide the true measure of immediate liquidity and period commercial performance.\n"
            "DISCRIMINATOR RULES:\n"
            "- VALUE TYPE: Absolute Currency (gross cash inflow from customers).\n"
            "- BASIS: Sector-specific (Real Estate / Lending / EPC) — represents raw cash inflow, NOT accounting revenue and NOT net operating cash flow.\n"
            "- NEVER MAP TO THIS BUCKET: Recognized Revenue (`accrual accounting, non-cash`); generic Operating Cash Flow / CFO (`net of vendor payments and taxes, NOT gross collections`); Pre-sales / Bookings (`contracts signed, but cash not yet collected`)."
        ),
        "layer2_rules": (
            "MANDATORY STEP-BY-STEP REAL ESTATE / INFRA VERIFICATION:\n"
            "1. STEP 1 (🚨 COLLECTIONS VS. PRE-SALES FIREWALL - CRITICAL): ACTIVATE KNOWLEDGE of Indian Real Estate (`e.g., DLF, Macrotech, Godrej Properties`). Real Estate companies report three distinct metrics: (1) Pre-sales/Bookings (`contracts signed`), (2) Collections (`cash received from clients against those contracts`), (3) Revenue (`accounting revenue recognized on project handover`). You MUST NOT confuse Collections with Pre-sales or Revenue. If the label says 'Pre-sales' or 'Sales Value', STRICTLY REJECT IT for this Collections bucket!\n"
            "2. STEP 2 (COLLECTIONS VS. CFO FIREWALL): Do NOT confuse gross customer Collections with statutory Ind AS 7 'Net cash generated from operating activities' (`CFO`). CFO subtracts payments to suppliers and taxes. Collections is a gross top-line cash metric. If the label is CFO, STRICTLY REJECT IT!\n"
            "3. STEP 3 (ANOMALY PREVENTION RULE): Do NOT grab subsidiary-specific project collections (`e.g., Note 39 water project user collections`) as group top-line collections. Must represent overall company customer collections."
        ),
    },
    {
        "name": "Pre-sales",
        "type": "Currency",
        "accept": ["Pre-sales", "Pre-sales Value", "Booking Value pre-revenue", "Contracted Sales", "Pre-launch Sales"],
        "reject": ["Revenue", "Recognized Revenue", "Order Backlog", "Bookings", "Collections", "Sales (recognized)"],
        "definition": (
            "The value of contracts signed or orders taken for products/services not yet delivered or recognized as revenue.\n"
            "DISCRIMINATOR RULES:\n"
            "- VALUE TYPE: Absolute Currency (value of contracts signed in the period).\n"
            "- BASIS: Sector-specific (real estate primarily) — distinct from both revenue recognition and cash collection.\n"
            "- NEVER MAP TO THIS BUCKET: recognized Revenue (already in the P&L); Bookings (→ Bookings — keep distinct by literal label); Collections (cash already received, separate bucket); Order Backlog (cumulative undelivered stock, not a period figure)."
        ),
    },
    {
        "name": "Bookings",
        "type": "Currency",
        "accept": ["Bookings", "Sales Bookings", "Gross Bookings", "Net Bookings", "Contracted Value", "Order Value", "New Order Inflow"],
        "reject": [
            "Order Backlog", "Order Book", "Revenue", "Recognized Revenue", "Pre-sales", "Collections",
            "Large Deal TCV", "Large deal bookings", "Segment deal TCV", "Segment bookings", "Large deals order intake"
        ],
        "definition": (
            "Total aggregate gross value of ALL new customer contracts, purchase orders, or client agreements signed across the entire company during the reporting period (`Order Intake` / `Total Contracted Pipeline`). It represents the full company-wide commercial inflow before revenue recognition (`Ind AS 115`).\n"
            "DISCRIMINATOR RULES (`WHOLE-COMPANY vs. DEAL TIER / SUB-SEGMENT REASONING`):\n"
            "- VALUE TYPE: Absolute Currency (value of new orders/contracts in the period — a flow, not a stock).\n"
            "- BASIS: Sector-specific (SaaS / industrial / services) — a forward indicator, not yet revenue.\n"
            "- WHOLE-COMPANY AGGREGATE ONLY: You must strictly verify whether a reported figure represents the entire company's total aggregate order intake across all operations (`Bookings`) versus only a specific deal-size tier (`Large Deal TCV` — e.g. Wipro's $3.9 Billion large deal TCV on P. 9), a specific business segment (`Digital segment bookings`), or cumulative multi-year undelivered stock (`Order Book / Backlog`).\n"
            "- SUB-SLICE REJECTION RULE: If a company reports only a headline figure for 'Large Deal TCV' or segment bookings, you must critically recognize that total company-wide aggregate bookings across all deal sizes are undisclosed. STRICTLY REJECT partial deal-tier sub-slices (`Large Deal TCV`) and return `null` when whole-company bookings are unavailable.\n"
            "- NEVER MAP TO THIS BUCKET: Order Backlog / Order Book (cumulative undelivered stock, not a period flow); Pre-sales (real-estate-specific, separate bucket); recognized Revenue; Collections (cash received)."
        ),
        "layer2_rules": (
            "WHOLE-COMPANY BOOKINGS PRUNING: You MUST ONLY select total company-wide aggregate order intake or total gross booking value across all operations. STRICTLY REJECT any candidate that represents only a partial sub-slice of total bookings, such as 'Large Deal TCV / Large deals order intake' (e.g. Wipro P. 9) or segment-specific bookings, unless total company-wide bookings are completely undisclosed."
        ),
    },
    {
        "name": "PPOP",
        "type": "Currency",
        "accept": ["PPOP", "Pre-Provisioning Operating Profit", "Profit before Provisions", "Operating Profit before provisions"],
        "reject": ["Net Profit", "PAT", "Operating Profit (non-banking)", "EBITDA", "EBIT", "NIM", "Net Interest Margin", "Provisions (the cost line itself)", "Credit Cost ex one-off"],
        "definition": (
            "Operating profit before deducting provisions for bad debts or loan losses. Primarily used in banking and NBFCs.\n"
            "DISCRIMINATOR RULES:\n"
            "- VALUE TYPE: Absolute Currency.\n"
            "- BASIS: Sector-specific (banking / NBFC / lending) — the label MUST imply 'before provisions'.\n"
            "- NEVER MAP TO THIS BUCKET: Net Profit / PAT (post-provisions); non-banking Operating Profit / EBITDA / EBIT (different aggregates); the provisions line itself or Credit Cost ex one-off (→ separate bucket); NIM or any margin percentage."
        ),
    },
    {
        "name": "Credit Cost ex one-off",
        "type": "Currency",
        "accept": [
            "Credit Cost excluding one-offs", "Credit Cost ex one-off", "Normalized Credit Cost", "Underlying Credit Cost", 
            "Provisions (excluding exceptional)", "Core Credit Cost"
        ],
        "reject": [
            "Total Provisions", "Gross NPA Provisions", "Provisions (gross)", "Credit Cost %", "Credit Cost ratio", 
            "PPOP", "Provisions and Contingencies"
        ],
        "definition": (
            "The absolute currency cost of credit (loan-loss provisions) excluding exceptional, non-recurring defaults or macro-prudential one-time provisioning overlays. It reflects the normalized recurring credit risk of a lending portfolio.\n"
            "DISCRIMINATOR RULES:\n"
            "- VALUE TYPE: Absolute Currency (a cost / provision amount — NEVER a percentage / basis-points ratio).\n"
            "- BASIS: Sector-specific (Banking / NBFC) — the Adjusted/Normalized variant of the absolute provision expense.\n"
            "- NEVER MAP TO THIS BUCKET: Statutory Gross Provisions (`NOT excluded of one-offs`); the Credit Cost Ratio / Credit Cost % (`basis points or %, NOT currency`); PPOP."
        ),
        "layer2_rules": (
            "MANDATORY STEP-BY-STEP BANKING PROVISION VERIFICATION:\n"
            "1. STEP 1 (🚨 CURRENCY VS. RATIO FIREWALL - CRITICAL): ACTIVATE KNOWLEDGE of Banking Disclosures (`e.g., HDFC Bank, Bajaj Finance`). Banks report 'Credit Cost' in TWO formats: absolute currency (`Rs. 5,000 Crores`) and a percentage ratio (`e.g., 'Credit Cost of 1.5% of advances'`). This bucket is STRICTLY for the absolute currency figure. If the candidate is a percentage (`%`) or basis points (`bps`), STRICTLY REJECT IT!\n"
            "2. STEP 2 (NORMALIZATION PROOF): The candidate MUST explicitly state 'excluding one-offs', 'normalized', or clearly deduct a specific exceptional provision (`e.g., 'COVID-19 contingency provision'`) from total provisions. Do NOT blindly grab the statutory 'Provisions and Contingencies' P&L line and claim it is ex-one-off!\n"
            "3. STEP 3 (DIRECTIONALITY): This is an expense. Treat it as a positive absolute cost figure, but verify its label."
        ),
    },
    {
        "name": "EVA",
        "type": "Currency",
        "accept": [
            "EVA", "Economic Value Added", "Economic Value Added (EVA)", "True Economic Profit"
        ],
        "reject": [
            "NOPAT", "ROIC", "Economic Profit (without EVA equivalence)", "Residual Income", 
            "MVA", "Market Value Added", "Capital Charge", "Cost of Capital", "Average Capital Employed"
        ],
        "definition": (
            "Economic Value Added (`EVA`): A proprietary financial metric showing the residual wealth created by a company after deducting the total cost of capital (`equity and debt`) from its operating profit.\n"
            "DISCRIMINATOR RULES:\n"
            "- VALUE TYPE: Absolute Currency (positive when value is created, negative when destroyed).\n"
            "- BASIS: The specific 'EVA' / 'Economic Value Added' label. Usually presented in a dedicated 'Value Added Statement' or Corporate Governance shareholder section.\n"
            "- NEVER MAP TO THIS BUCKET: NOPAT (`the starting operating profit input`); Capital Charge (`the subtracted cost input`); MVA / Market Value Added (`a market-cap metric, not an operating metric`); ROIC (`a percentage return ratio`)."
        ),
        "layer2_rules": (
            "MANDATORY STEP-BY-STEP ACCOUNTING & MATHEMATICAL VERIFICATION:\n"
            "1. STEP 1 (🚨 RECONCILIATION TABLE INPUT TRAP - CRITICAL): ACTIVATE KNOWLEDGE of Corporate Governance Value Added Statements. EVA is calculated via a multi-row schedule: `NOPAT minus Capital Charge = EVA`. When evaluating candidates from an EVA table, you MUST NEVER grab the starting row (`NOPAT / Net Operating Profit After Tax`) or the middle deduction row (`Capital Charge / Cost of Capital`). You MUST explicitly select the final calculated ending row labeled 'Economic Value Added'!\n"
            "2. STEP 2 (MVA DISTRACTOR EXCLUSION): Companies often report MVA (`Market Value Added`) on the exact same page or next page as EVA. MVA is calculated as Market Capitalization minus Equity. STRICTLY REJECT MVA! Ensure the label explicitly says 'Economic Value Added' or 'EVA'."
        ),
    },
    {
        "name": "Cash Earnings",
        "type": "Currency",
        "accept": ["Cash Earnings", "Cash Profit", "Cash PAT", "Cash Net Income"],
        "reject": ["EBITDA", "CFO", "Operating Cash Flow", "Net Profit", "PAT", "Free Cash Flow", "FCF", "Cash Loss", "Adjusted Earnings"],
        "definition": (
            "Net income plus non-cash charges like depreciation and amortization. Represents the cash-generating capability of accrual profit.\n"
            "DISCRIMINATOR RULES:\n"
            "- VALUE TYPE: Absolute Currency (a positive earnings figure — NEVER a cash-flow-statement line).\n"
            "- BASIS: The specific 'Cash Earnings' / 'Cash Profit' label — distinct from cash-flow-statement aggregates.\n"
            "- NEVER MAP TO THIS BUCKET: EBITDA (similar idea but a different starting point and adjustments); Operating Cash Flow / CFO (a cash-flow-statement line); plain Net Profit / PAT (accrual); Free Cash Flow (post-CapEx); Cash Loss (the negative counterpart — separate bucket); Adjusted Earnings (different qualifier semantics)."
        ),
        "layer2_rules": (
            "MANDATORY STEP-BY-STEP VERIFICATION:\n"
            "1. STEP 1 (VERBATIM & FORMULA CHECK): You are evaluating Cash Earnings (Cash Profit / Cash PAT). This is statutorily defined as PAT + Depreciation & Amortization. Do not grab Operating Cash Flow (CFO) from the Cash Flow Statement!\n"
            "2. STEP 2 (PRECISION CHECK): If both a rounded summary table figure and an exact unrounded narrative/table figure exist, prefer the exact unrounded figure or primary table.\n"
            "3. STEP 3 (SCOPE PRUNING): Prefer Consolidated over Standalone for the overall company."
        ),
    },
    {
        "name": "Cash Loss",
        "type": "Currency",
        "accept": ["Cash Loss", "Cash Loss numeric value", "Cash Operating Loss"],
        "reject": ["Accounting Loss", "Net Loss", "Book Loss", "Cash Loss Incurrence Status", "Cash Earnings", "Operating Loss"],
        "definition": (
            "A situation where the actual cash outflows from operations exceed inflows, regardless of non-cash accounting entries.\n"
            "DISCRIMINATOR RULES:\n"
            "- VALUE TYPE: Absolute Currency (the numeric magnitude of the cash loss — a number, NOT a yes/no statement).\n"
            "- BASIS: A specific 'Cash Loss' label with an accompanying numeric figure.\n"
            "- NEVER MAP TO THIS BUCKET: Net Loss / Accounting Loss / Book Loss (accrual-basis, separate concept); Cash Loss Incurrence Status (→ a yes/no Boolean disclosure, separate bucket); positive Cash Earnings (the opposite sign)."
        ),
        "layer2_rules": (
            "VERBATIM & FORMULA CHECK: You are evaluating Cash Loss (the numeric magnitude of negative cash profit or cash operating outflow). Do not grab accrual Net Loss or Book Loss. STRICT BAN: NEVER select Operating Cash Flow (CFO / Net cash inflow/outflow from operating activities) from the Cash Flow Statement!"
        ),
    },
    {
        "name": "Cash Loss Incurrence Status",
        "type": "Boolean",
        "accept": ["No cash loss incurred", "Cash loss not incurred", "Company has not incurred cash loss", "Cash loss incurred during the year", "The company has incurred cash loss"],
        "reject": ["Numeric cash loss values", "Cash Loss (with a number)", "Net Loss declarations", "Going-concern statements", "Profitability statements"],
        "definition": (
            "A binary disclosure of whether the auditors or management explicitly state that a cash loss occurred during the period.\n"
            "DISCRIMINATOR RULES:\n"
            "- VALUE TYPE: Boolean (a yes/no statement — the value carries a true/false signal, NOT a number).\n"
            "- BASIS: An explicit narrative disclosure tying cash loss to the reporting period.\n"
            "- NEVER MAP TO THIS BUCKET: any numeric cash loss value (→ Cash Loss); accrual-basis Net Loss declarations; going-concern boilerplate that does not specifically address cash loss; general profitability statements."
        ),
        "layer2_rules": (
            "BOOLEAN STATUS CHECK: You are evaluating whether the company incurred a cash loss. Look specifically in the Statutory Auditor's Report (e.g., under CARO requirements). If the Auditor's Report explicitly states 'The Company has not incurred any cash losses during the financial year', set final_value to 'false'. If it states cash losses were incurred, set final_value to 'true'."
        ),
    },
]


# Set of names for cheap membership checks downstream
METRIC_NAMES: frozenset[str] = frozenset(m["name"] for m in METRIC_METADATA)

# Define logical groups to batch queries (reduces 37 calls to 4 calls)
METRIC_GROUPS: dict[str, list[str]] = {
    "Group_A_Profitability_Margins": [
        "Adjusted Revenue", "Adjusted Earnings", "Normalized Earnings", "Core Earnings", 
        "Recurring Earnings", "Adjusted EPS", "Normalized EPS", "EBIT", "EBITDA", 
        "Adjusted EBIT", "Adjusted EBITDA", "Core Operating Profit", "EBIT Margin", 
        "EBITDA Margin", "Base Business Margin", "Adjusted ROE", "Adjusted ROA"
    ],
    "Group_B_Cash_Flow_Debt": [
        "Free Cash Flow (FCF)", "Funds From Operations (FFO)", "Distributable Cash Flow", 
        "Net Debt", "Net Surplus Cash", "Cash Earnings", "Cash Loss", "Cash Loss Incurrence Status"
    ],
    "Group_C_Currency_GAAP": [
        "Constant Currency Revenue", "Constant Currency Revenue Growth", "Constant Currency Opex", 
        "GAAP One-time Adjustment", "GAAP Adjusted"
    ],
    "Group_D_Sector_Specific": [
        "ARPU", "Collections", "Pre-sales", "Bookings", "PPOP", "Credit Cost ex one-off", "EVA"
    ]
}

# Verify that every metric in METRIC_METADATA belongs to exactly one group
_all_grouped = [name for group_list in METRIC_GROUPS.values() for name in group_list]
assert len(_all_grouped) == 37, f"Expected 37 metrics in groups, got {len(_all_grouped)}"
assert set(_all_grouped) == METRIC_NAMES, f"Grouped metrics do not match METRIC_NAMES: {set(_all_grouped) ^ METRIC_NAMES}"

