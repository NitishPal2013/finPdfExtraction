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
    },
    {
        "name": "Normalized Earnings",
        "type": "Currency",
        "accept": ["Normalized Earnings", "Normalized PAT", "Normalized Net Income", "Normalized Profit", "Normalized Profit After Tax"],
        "reject": ["Adjusted Earnings", "Adjusted PAT", "Core Earnings", "Core PAT", "Recurring Earnings", "Reported PAT", "Net Profit", "Net Income", "Basic Earnings", "Normalized EPS", "Normalized EBITDA", "Normalized Credit Cost"],
        "definition": (
            "Earnings calculated by smoothing out fluctuations or one-off items to reflect a 'steady-state' profit level.\n"
            "DISCRIMINATOR RULES:\n"
            "- VALUE TYPE: Absolute Currency (a total Rs/USD bottom-line figure — NEVER per-share, NEVER a percentage).\n"
            "- BASIS: Normalized — the printed label MUST literally contain 'Normalized' attached to Earnings / PAT / Net Income / Net Profit.\n"
            "- NEVER MAP TO THIS BUCKET: 'Adjusted X' (→ Adjusted Earnings) and 'Core X' / 'Recurring X' (separate buckets) — route by the exact qualifier word; Reported PAT / Net Income (statutory); Normalized EPS (per-share, separate); Normalized EBITDA / Normalized Credit Cost (different financial concepts)."
        ),
    },
    {
        "name": "Core Earnings",
        "type": "Currency",
        "accept": ["Core Earnings", "Core PAT", "Core Net Income", "Core Profit", "Underlying Profit"],
        "reject": ["Adjusted Earnings", "Normalized Earnings", "Recurring Earnings", "Net Income", "Net Profit", "Reported PAT", "EBITDA", "Core Operating Profit", "Core Margin", "Base Business Margin", "Core Revenue"],
        "definition": (
            "Profit derived solely from the primary business activities, excluding investment income or secondary operations.\n"
            "DISCRIMINATOR RULES:\n"
            "- VALUE TYPE: Absolute Currency at the bottom-line / earnings level (NEVER a margin, NEVER operating-profit level, NEVER per-share).\n"
            "- BASIS: Core/Underlying — the printed label MUST literally contain 'Core' or 'Underlying' attached to Earnings / PAT / Profit / Net Income.\n"
            "- NEVER MAP TO THIS BUCKET: 'Adjusted X' / 'Normalized X' / 'Recurring X' (route by the literal qualifier word — each is its own bucket); plain Net Income / Reported PAT (statutory); EBITDA (operating cash-flow proxy, not bottom-line); 'Core Operating Profit' (operating-level, separate bucket); 'Core Margin' / 'Base Business Margin' (percentages, separate)."
        ),
    },
    {
        "name": "Recurring Earnings",
        "type": "Currency",
        "accept": ["Recurring Earnings", "Recurring PAT", "Recurring Profit", "Recurring Net Income"],
        "reject": ["Adjusted Earnings", "Normalized Earnings", "Core Earnings", "Implied Earnings", "Forecasted Earnings", "Projected Earnings", "Net Profit", "Net Income", "Reported PAT"],
        "definition": (
            "Earnings that are expected to repeat in future periods, strictly excluding non-recurring windfalls or losses.\n"
            "DISCRIMINATOR RULES:\n"
            "- VALUE TYPE: Absolute Currency (NEVER a percentage, NEVER per-share).\n"
            "- BASIS: Recurring — the printed label MUST literally contain 'Recurring' attached to Earnings / PAT / Profit / Net Income.\n"
            "- NEVER MAP TO THIS BUCKET: 'Adjusted X' / 'Normalized X' / 'Core X' (separate buckets — match the literal qualifier on the page); forecasted/implied/projected earnings (forward-looking, not actual); plain Net Profit / Reported PAT (statutory)."
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
    },
    {
        "name": "Normalized EPS",
        "type": "Currency",
        "accept": ["Normalized EPS", "Normalized Earnings Per Share", "Normalized Diluted EPS"],
        "reject": ["Reported EPS", "Basic EPS", "Diluted EPS", "Adjusted EPS", "Cash EPS", "Normalized Earnings", "Normalized PAT"],
        "definition": (
            "EPS based on normalized earnings to provide a comparable baseline across reporting periods.\n"
            "DISCRIMINATOR RULES:\n"
            "- VALUE TYPE: Per-Share Currency (a small Rs/USD figure per share — NEVER a total company figure).\n"
            "- BASIS: Normalized — the printed label MUST literally contain 'Normalized' attached to EPS / Earnings Per Share.\n"
            "- NEVER MAP TO THIS BUCKET: Adjusted EPS / Basic EPS / Diluted EPS / Reported EPS (each its own bucket — match the literal qualifier); Normalized Earnings (absolute total, not per-share)."
        ),
    },
    {
        "name": "GAAP One-time Adjustment",
        "type": "Currency",
        "accept": ["GAAP one-time adjustment", "One-time GAAP adjustment", "Exceptional GAAP adjustment", "Non-recurring GAAP item (with numeric value)"],
        "reject": ["Narrative-only descriptions", "Generic exceptional items (no GAAP context)", "Ongoing/recurring adjustments", "GAAP Adjusted (the full adjusted figure)", "Adjusted Earnings"],
        "definition": (
            "Specific numerical adjustments made to reconcile statutory figures to a standardized GAAP presentation.\n"
            "DISCRIMINATOR RULES:\n"
            "- VALUE TYPE: Absolute Currency adjustment amount with an explicit numeric value (NEVER a narrative-only description).\n"
            "- BASIS: A single named GAAP reconciliation item — one-time / exceptional in nature.\n"
            "- NEVER MAP TO THIS BUCKET: generic 'exceptional items' without a GAAP-anchor label; full Adjusted Earnings / Adjusted EBITDA aggregates; ongoing recurring adjustments; the GAAP Adjusted post-reconciliation total (→ GAAP Adjusted)."
        ),
    },
    {
        "name": "GAAP Adjusted",
        "type": "Currency",
        "accept": ["GAAP Pro-forma", "GAAP Normalized", "GAAP Adjusted", "GAAP-Adjusted Earnings"],
        "reject": ["Non-GAAP metrics", "Non-GAAP Earnings", "Plain Adjusted Earnings (no GAAP anchor)", "GAAP One-time Adjustment (a component, not the total)"],
        "definition": (
            "Financial figures adjusted within the bounds of GAAP principles rather than using internal management metrics.\n"
            "DISCRIMINATOR RULES:\n"
            "- VALUE TYPE: Absolute Currency post-reconciliation figure presented as 'GAAP-Adjusted' / 'GAAP Pro-forma' / 'GAAP Normalized'.\n"
            "- BASIS: GAAP-anchored adjustment — explicitly distinct from Non-GAAP management metrics.\n"
            "- NEVER MAP TO THIS BUCKET: Non-GAAP figures; plain 'Adjusted Earnings' / 'Adjusted EBITDA' without a GAAP-anchor label (those belong to their own buckets); the one-time adjustment component (→ GAAP One-time Adjustment)."
        ),
    },
    {
        "name": "EBIT",
        "type": "Currency",
        "accept": ["EBIT", "PBIT", "Operating Profit", "Profit before interest and tax"],
        "reject": ["EBITDA", "PBITDA", "PBT", "Profit before tax", "Segment Result", "Adjusted EBIT", "Normalized EBIT", "Underlying EBIT", "EBIT before exceptional items", "EBIT Margin", "Operating Profit Margin"],
        "definition": (
            "Earnings Before Interest and Taxes. Operating profit before financing costs and tax obligations.\n"
            "DISCRIMINATOR RULES:\n"
            "- VALUE TYPE: Absolute Currency (NEVER a percentage).\n"
            "- BASIS: Reported/Statutory — the raw EBIT figure. The printed label MUST NOT carry an 'Adjusted' / 'Normalized' / 'Pro-forma' / 'Core' / 'Underlying' qualifier (those route to Adjusted EBIT).\n"
            "- LABEL / COMPONENT REQUIREMENT: Look for labels such as 'EBIT', 'PBIT', 'Operating Profit', 'Profit before interest and tax'. The figure must be after operating items but BEFORE interest and tax (D and A have already been subtracted if present).\n"
            "- NEVER MAP TO THIS BUCKET: EBITDA (the 'D' and 'A' matter — do NOT cross-map); Adjusted/Normalized/Underlying EBIT (→ Adjusted EBIT); EBIT Margin (percentage, separate bucket); PBT / Profit before tax (different point in the P&L); Segment Result (segment-level, out of scope per the SEGMENT-QUALIFIED LABELS rule)."
        ),
    },
    {
        "name": "EBITDA",
        "type": "Currency",
        "accept": ["EBITDA", "PBITDA", "Operating EBITDA"],
        "reject": ["EBIT", "PBIT", "Cash Profit", "PAT", "Adjusted EBITDA", "Normalized EBITDA", "Pro-forma EBITDA", "Underlying EBITDA", "EBITDA Margin", "Segment EBITDA"],
        "definition": (
            "Earnings Before Interest, Taxes, Depreciation, and Amortization. A proxy for operational cash flow before capital reinvestment.\n"
            "DISCRIMINATOR RULES:\n"
            "- VALUE TYPE: Absolute Currency (NEVER a percentage).\n"
            "- BASIS: Reported/Statutory — the raw EBITDA figure. The printed label MUST NOT carry an 'Adjusted' / 'Normalized' / 'Pro-forma' / 'Underlying' qualifier (those route to Adjusted EBITDA).\n"
            "- LABEL / COMPONENT REQUIREMENT: Prefer direct labels ('EBITDA', 'PBITDA', 'Operating EBITDA') OR labels that represent 'Profit before Depreciation, Interest and Tax (and Amortization)'. The value must correspond to earnings with D+A (and usually I+T) not yet subtracted.\n"
            "- NEVER MAP TO THIS BUCKET: EBIT (Depreciation & Amortization are NOT subtracted in EBITDA — letters matter); Adjusted/Normalized/Pro-forma EBITDA (→ Adjusted EBITDA); EBITDA Margin (percentage, separate bucket); Cash Profit / PAT (different metrics entirely); segment-level or business-line EBITDA."
        ),
    },
    {
        "name": "Adjusted EBIT",
        "type": "Currency",
        "accept": ["Adjusted EBIT", "Normalized EBIT", "Underlying EBIT", "EBIT before exceptional items", "Pro-forma EBIT"],
        "reject": ["Reported EBIT", "plain EBIT", "PBIT (plain)", "EBITDA", "Adjusted EBITDA", "Adjusted EBIT Margin", "Adjusted Operating Profit Margin", "Segment EBIT"],
        "definition": (
            "EBIT adjusted for non-recurring operational items to show the 'clean' operating performance.\n"
            "DISCRIMINATOR RULES:\n"
            "- VALUE TYPE: Absolute Currency (NEVER a percentage / margin).\n"
            "- BASIS: Adjusted/Normalized — the printed label MUST literally contain 'Adjusted' / 'Normalized' / 'Underlying' / 'Pro-forma' / 'before exceptional items' alongside 'EBIT'.\n"
            "- NEVER MAP TO THIS BUCKET: plain/Reported EBIT (→ EBIT); EBITDA / Adjusted EBITDA (the 'D' and 'A' matter); EBIT Margin or Adjusted EBIT Margin (percentages — there is no dedicated 'Adjusted EBIT Margin' bucket, so return null per the QUALIFIERS rule); segment-level EBIT."
        ),
    },
    {
        "name": "Adjusted EBITDA",
        "type": "Currency",
        "accept": ["Adjusted EBITDA", "Normalized EBITDA", "Pro-forma EBITDA", "Underlying EBITDA", "EBITDA before exceptional items"],
        "reject": ["Plain EBITDA", "Reported EBITDA", "PBITDA (plain)", "EBIT", "Adjusted EBIT", "Adjusted EBITDA Margin", "Normalized EBITDA Margin", "Cash Profit", "Segment EBITDA"],
        "definition": (
            "EBITDA further refined to exclude items like restructuring costs, stock-based compensation, or legal settlements.\n"
            "DISCRIMINATOR RULES:\n"
            "- VALUE TYPE: Absolute Currency (NEVER a percentage / margin).\n"
            "- BASIS: Adjusted/Normalized/Pro-forma — the printed label MUST literally contain one of these qualifiers alongside 'EBITDA'.\n"
            "- NEVER MAP TO THIS BUCKET: plain/Reported EBITDA (→ EBITDA); EBIT or Adjusted EBIT (the 'D' and 'A' matter); EBITDA Margin / Adjusted EBITDA Margin (percentages — there is no dedicated 'Adjusted EBITDA Margin' bucket, so return null per the QUALIFIERS rule); Cash Profit; segment-level EBITDA."
        ),
    },
    {
        "name": "Core Operating Profit",
        "type": "Currency",
        "accept": ["Core Operating Profit", "Underlying Operating Profit"],
        "reject": ["Segment Result", "Operating Profit (plain)", "EBIT", "EBITDA", "Adjusted EBIT", "Core Earnings", "Core Margin", "Base Business Margin"],
        "definition": (
            "The profit from primary operations only, excluding group-level adjustments or non-core business segments.\n"
            "DISCRIMINATOR RULES:\n"
            "- VALUE TYPE: Absolute Currency at the operating-profit level (NEVER a margin, NEVER a bottom-line earnings figure).\n"
            "- BASIS: Core — the printed label MUST literally contain 'Core Operating' or 'Underlying Operating'.\n"
            "- NEVER MAP TO THIS BUCKET: plain Operating Profit (→ EBIT); EBITDA (different aggregate); Adjusted EBIT (→ Adjusted EBIT — different qualifier); 'Core Earnings' (bottom-line, separate bucket); Segment Result (segment-level, out of scope); any percentage margin including Core Margin / Base Business Margin."
        ),
    },
    {
        "name": "EBIT Margin",
        "type": "Percentage",
        "accept": ["EBIT Margin", "EBIT Margin %", "Operating Profit Margin", "Operating Profit Margin %", "Operating Margin", "PBIT Margin"],
        "reject": ["EBITDA Margin", "Net Profit Margin", "Gross Margin", "Adjusted EBIT Margin", "Normalized EBIT Margin", "Underlying EBIT Margin", "EBIT", "Adjusted EBIT", "Segment EBIT Margin"],
        "definition": (
            "EBIT expressed as a percentage of total revenue. Measures operational efficiency.\n"
            "DISCRIMINATOR RULES:\n"
            "- VALUE TYPE: Percentage / Margin Ratio (always 'x.x%' alongside the word 'Margin'). NEVER an absolute currency amount.\n"
            "- BASIS: Reported/Statutory — the raw EBIT margin. The printed label MUST NOT carry 'Adjusted' / 'Normalized' / 'Pro-forma' / 'Underlying' qualifiers. There is no 'Adjusted EBIT Margin' bucket in this dictionary, so qualifier-stripping is forbidden — return null if only the adjusted version appears.\n"
            "- NEVER MAP TO THIS BUCKET: EBITDA Margin (letter 'D' matters); Net Profit Margin / Gross Margin (different aggregates); absolute EBIT figures (→ EBIT) or Adjusted EBIT (→ Adjusted EBIT); 'Adjusted EBIT Margin' (forbidden qualifier-strip)."
        ),
    },
    {
        "name": "EBITDA Margin",
        "type": "Percentage",
        "accept": ["EBITDA Margin", "EBITDA Margin %", "PBITDA Margin", "Operating EBITDA Margin"],
        "reject": ["EBIT Margin", "Net Profit Margin", "Gross Margin", "Adjusted EBITDA Margin", "Normalized EBITDA Margin", "Pro-forma EBITDA Margin", "Underlying EBITDA Margin", "EBITDA", "Adjusted EBITDA", "Segment EBITDA Margin"],
        "definition": (
            "EBITDA as a percentage of revenue. Used to compare profitability across companies with different capital structures.\n"
            "DISCRIMINATOR RULES:\n"
            "- VALUE TYPE: Percentage / Margin Ratio (always 'x.x%' alongside the word 'Margin'). NEVER an absolute currency amount.\n"
            "- BASIS: Reported/Statutory — the raw EBITDA margin. The printed label MUST NOT carry 'Adjusted' / 'Normalized' / 'Pro-forma' / 'Underlying' qualifiers. There is no 'Adjusted EBITDA Margin' bucket in this dictionary, so qualifier-stripping is forbidden — if only the adjusted version appears on the page, return null.\n"
            "- NEVER MAP TO THIS BUCKET: EBIT Margin ('D' and 'A' matter); Net Profit Margin / Gross Margin (different aggregates); absolute EBITDA figures (→ EBITDA) or Adjusted EBITDA (→ Adjusted EBITDA); 'Adjusted/Normalized/Pro-forma EBITDA Margin' (forbidden qualifier-strip)."
        ),
    },
    {
        "name": "Base Business Margin",
        "type": "Percentage",
        "accept": ["Base Business Margin", "Core Margin", "Base Margin", "Core Business Margin"],
        "reject": ["Gross Margin", "EBITDA Margin", "EBIT Margin", "Operating Margin", "Net Margin", "Net Profit Margin", "Core Earnings", "Core Operating Profit", "Segment Margin"],
        "definition": (
            "Profit margin specifically for the legacy or core business units, excluding new acquisitions or hyper-growth segments.\n"
            "DISCRIMINATOR RULES:\n"
            "- VALUE TYPE: Percentage / Margin Ratio (NEVER absolute currency).\n"
            "- BASIS: Reported margin for the core/legacy business — distinct from group-level or segment margins.\n"
            "- NEVER MAP TO THIS BUCKET: Gross Margin / EBITDA Margin / EBIT Margin / Net Margin (each is its own concept); 'Core Earnings' / 'Core Operating Profit' (absolute currency, not margin); segment-level margins (out of scope per the SEGMENT-QUALIFIED LABELS rule)."
        ),
    },
    {
        "name": "Adjusted ROE",
        "type": "Percentage",
        "accept": ["Adjusted ROE", "Adjusted Return on Equity", "Normalized ROE", "Underlying ROE"],
        "reject": ["Reported ROE", "plain ROE", "ROCE", "ROIC", "RONA", "Adjusted ROA", "Return on Equity (no qualifier)", "Net Income", "Total Equity"],
        "definition": (
            "Return on Equity calculated using adjusted net income to show management's efficiency in generating profit from equity.\n"
            "DISCRIMINATOR RULES:\n"
            "- VALUE TYPE: Percentage / Return Ratio (NEVER absolute currency).\n"
            "- BASIS: Adjusted/Normalized — the printed label MUST literally contain 'Adjusted' / 'Normalized' / 'Underlying' alongside 'ROE' / 'Return on Equity'.\n"
            "- NEVER MAP TO THIS BUCKET: plain/Reported ROE (no dedicated bucket — return null per the QUALIFIERS rule); ROCE / ROIC / RONA / Adjusted ROA (each has a different denominator); absolute net income or equity figures."
        ),
    },
    {
        "name": "Adjusted ROA",
        "type": "Percentage",
        "accept": ["Adjusted ROA", "Adjusted Return on Assets", "Normalized ROA", "Underlying ROA"],
        "reject": ["Reported ROA", "plain ROA", "RONA", "ROE", "Adjusted ROE", "ROCE", "ROIC", "Return on Assets (no qualifier)", "Net Income", "Total Assets"],
        "definition": (
            "Return on Assets using adjusted figures to evaluate asset utilization without the noise of one-time charges.\n"
            "DISCRIMINATOR RULES:\n"
            "- VALUE TYPE: Percentage / Return Ratio (NEVER absolute currency).\n"
            "- BASIS: Adjusted/Normalized — the printed label MUST literally contain 'Adjusted' / 'Normalized' / 'Underlying' alongside 'ROA' / 'Return on Assets'.\n"
            "- NEVER MAP TO THIS BUCKET: plain/Reported ROA (no dedicated bucket — return null per the QUALIFIERS rule); ROE / Adjusted ROE / RONA / ROCE / ROIC (different denominators); absolute net income or asset figures."
        ),
    },
    {
        "name": "Free Cash Flow (FCF)",
        "type": "Currency",
        "accept": ["Free Cash Flow", "FCF"],
        "reject": ["CFO", "Cash from Operations", "Operating Cash Flow", "FCFE", "FCFF", "Funds From Operations", "FFO", "Distributable Cash Flow", "Cash from Investing", "Cash from Financing"],
        "definition": (
            "Operating cash flow minus capital expenditures (CapEx). Represents cash available for distribution or debt reduction.\n"
            "DISCRIMINATOR RULES:\n"
            "- VALUE TYPE: Absolute Currency (a cash-flow figure).\n"
            "- BASIS: The specific 'Free Cash Flow' / 'FCF' label — NOT a generic 'cash' line. Look for explicit presentation or reconciliation that isolates FCF for the target period.\n"
            "- NEVER MAP TO THIS BUCKET: Operating Cash Flow / CFO (broader, pre-CapEx — separate concept); Funds From Operations / FFO (→ FFO); Distributable Cash Flow (→ Distributable Cash Flow); FCFE / FCFF variants (equity vs firm — out of scope here); generic Cash & Cash Equivalents."
        ),
    },
    {
        "name": "Funds From Operations (FFO)",
        "type": "Currency",
        "accept": ["Funds From Operations", "FFO"],
        "reject": ["AFFO", "Adjusted FFO", "Free Cash Flow", "FCF", "Cash from Operations", "CFO", "Distributable Cash Flow", "Operating Cash Flow"],
        "definition": (
            "A measure of cash generated by real estate or investment activities, excluding gains/losses from property sales.\n"
            "DISCRIMINATOR RULES:\n"
            "- VALUE TYPE: Absolute Currency.\n"
            "- BASIS: The specific 'Funds From Operations' / 'FFO' label — sector-specific (REITs / investment trusts).\n"
            "- NEVER MAP TO THIS BUCKET: AFFO / Adjusted FFO (different, downstream metric); Free Cash Flow / FCF (separate); generic Operating Cash Flow / CFO; Distributable Cash Flow."
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
    },
    {
        "name": "Net Debt",
        "type": "Currency",
        "accept": ["Net Debt", "Net Borrowings", "Net Financial Debt", "Net Indebtedness"],
        "reject": ["Gross Debt", "Total Debt", "Total Borrowings", "Total Liabilities", "Long-term Borrowings", "Short-term Borrowings", "Net Cash Position", "Net Surplus Cash"],
        "definition": (
            "Total financial debt minus cash and cash equivalents. Shows the true leverage of the company.\n"
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
        "accept": ["Constant Currency Revenue", "CC Revenue", "FX-neutral Revenue", "Revenue in constant currency terms"],
        "reject": ["Reported Revenue", "Total Revenue", "plain Revenue", "Adjusted Revenue", "Constant Currency Revenue Growth", "CC Revenue Growth %", "Organic Revenue"],
        "definition": (
            "Revenue calculated by eliminating the effect of foreign exchange rate fluctuations.\n"
            "DISCRIMINATOR RULES:\n"
            "- VALUE TYPE: Absolute Currency (a revenue figure — NEVER a percentage growth rate).\n"
            "- BASIS: Constant-Currency / FX-neutral — the printed label MUST literally contain 'Constant Currency' / 'CC' / 'FX-neutral' alongside Revenue.\n"
            "- NEVER MAP TO THIS BUCKET: Reported / Total / plain Revenue (statutory — separate); Adjusted Revenue (management-adjusted, not FX-neutral); Constant Currency Revenue Growth (→ the percentage bucket, NOT this absolute figure)."
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
        "accept": ["Constant Currency Opex", "CC Opex", "FX-neutral Opex", "Operating Expenses in constant currency"],
        "reject": ["Reported Opex", "Total Opex", "Opex Growth %", "Constant Currency Revenue", "Cost of Revenue (no FX qualifier)"],
        "definition": (
            "Operating expenses calculated at fixed exchange rates to evaluate cost-management performance.\n"
            "DISCRIMINATOR RULES:\n"
            "- VALUE TYPE: Absolute Currency (an expense figure — NEVER a percentage).\n"
            "- BASIS: Constant-Currency / FX-neutral — the printed label MUST literally contain 'Constant Currency' / 'CC' / 'FX-neutral' alongside 'Opex' / 'Operating Expenses'.\n"
            "- NEVER MAP TO THIS BUCKET: reported / total Opex (no FX qualifier); percentage Opex growth; Constant Currency Revenue (a different P&L line)."
        ),
    },
    {
        "name": "ARPU",
        "type": "Currency",
        "accept": ["ARPU", "Average Revenue Per User", "Average Revenue Per Subscriber"],
        "reject": ["ARPPU", "Average Revenue Per Paying User", "Revenue per unit", "Revenue per Employee", "Total Revenue", "Subscriber count"],
        "definition": (
            "Average Revenue Per User. A key metric for subscription or telecommunication businesses.\n"
            "DISCRIMINATOR RULES:\n"
            "- VALUE TYPE: Per-User Currency (a small Rs/USD figure per user/subscriber per period — NEVER a total revenue figure in millions/billions).\n"
            "- BASIS: Sector-specific (telecom / subscription / SaaS).\n"
            "- NEVER MAP TO THIS BUCKET: ARPPU (Average Revenue Per Paying User — a stricter cohort); Revenue per Unit / Revenue per Employee (different denominators); total revenue figures; subscriber counts (unit counts, not currency)."
        ),
    },
    {
        "name": "Collections",
        "type": "Currency",
        "accept": ["Collections", "Sales Collections", "Cash Collections", "Customer Collections", "Collection Value"],
        "reject": ["Revenue", "Revenue from Operations", "CFO", "Operating Cash Flow", "Receipts (generic)", "Order Book", "Order Backlog", "Pre-sales", "Bookings"],
        "definition": (
            "Actual cash received from customers during the period, distinct from recognized revenue which may be on credit.\n"
            "DISCRIMINATOR RULES:\n"
            "- VALUE TYPE: Absolute Currency (cash collected in the period).\n"
            "- BASIS: Sector-specific (real estate / lending / infra) — cash inflows from customers, NOT accrual revenue and NOT CFO.\n"
            "- NEVER MAP TO THIS BUCKET: recognized Revenue (accrual basis, not cash); generic Operating Cash Flow / CFO (broader); Order Book / Backlog (a stock, not a period flow); Pre-sales / Bookings (contracted but not yet collected — separate buckets)."
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
        "reject": ["Order Backlog", "Order Book", "Revenue", "Recognized Revenue", "Pre-sales", "Collections"],
        "definition": (
            "Total value of new contracts or orders secured during the period, indicating future revenue pipeline.\n"
            "DISCRIMINATOR RULES:\n"
            "- VALUE TYPE: Absolute Currency (value of new orders/contracts in the period — a flow, not a stock).\n"
            "- BASIS: Sector-specific (SaaS / industrial / services) — a forward indicator, not yet revenue.\n"
            "- NEVER MAP TO THIS BUCKET: Order Backlog / Order Book (cumulative undelivered stock, not a period flow); Pre-sales (real-estate-specific, separate bucket); recognized Revenue; Collections (cash received)."
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
        "accept": ["Credit Cost excluding one-offs", "Credit Cost ex one-off", "Normalized Credit Cost", "Underlying Credit Cost"],
        "reject": ["Total Provisions", "Gross NPA Provisions", "Provisions (gross)", "Credit Cost %", "Credit Cost ratio", "PPOP"],
        "definition": (
            "The cost of credit (loan-loss provisions) excluding exceptional or non-recurring defaults.\n"
            "DISCRIMINATOR RULES:\n"
            "- VALUE TYPE: Absolute Currency (a cost / provision amount — NEVER a percentage / basis-points ratio).\n"
            "- BASIS: Sector-specific (banking / NBFC) — the Adjusted/Normalized variant of credit cost.\n"
            "- NEVER MAP TO THIS BUCKET: gross / total Provisions (NOT excluded of one-offs); the Credit Cost ratio / Credit Cost % (basis points or %); PPOP (→ separate banking aggregate)."
        ),
    },
    {
        "name": "EVA",
        "type": "Currency",
        "accept": ["EVA", "Economic Value Added"],
        "reject": ["NOPAT", "ROIC", "Economic Profit (without EVA equivalence)", "Residual Income", "MVA", "Market Value Added"],
        "definition": (
            "Economic Value Added: the residual wealth left after deducting the cost of capital from operating profit. Indicates true value creation.\n"
            "DISCRIMINATOR RULES:\n"
            "- VALUE TYPE: Absolute Currency (positive when value is created, negative when destroyed).\n"
            "- BASIS: The specific 'EVA' / 'Economic Value Added' label.\n"
            "- NEVER MAP TO THIS BUCKET: NOPAT (an input to EVA, not EVA itself); ROIC (a ratio, not currency); generic 'Economic Profit' unless the document explicitly equates it to EVA; Residual Income (related but distinct framework); MVA / Market Value Added."
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
    },
]


# Set of names for cheap membership checks downstream
METRIC_NAMES: frozenset[str] = frozenset(m["name"] for m in METRIC_METADATA)
