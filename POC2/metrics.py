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
    {"name": "Adjusted Revenue", "type": "Currency", "accept": ["Adjusted Revenue", "Normalized Revenue", "Pro-forma Revenue", "Core Revenue", "Non-GAAP Revenue"], "reject": ["Reported Revenue", "Total Revenue"], "definition": "Revenue adjusted by management for one-time events, non-recurring items, or discontinued operations to show core top-line performance."},
    {
        "name": "Adjusted Earnings", 
        "type": "Currency", 
        "accept": ["Adjusted PAT", "Normalized PAT", "Underlying Earnings", "Core PAT"], 
        "reject": ["PAT before exceptional items", "Reported PAT", "Net Profit", "Net Income"], 
        "definition": "The bottom-line profit after adjusting for non-cash items, exceptional costs, and tax anomalies. CRITICAL DISTINCTION: This must explicitly represent an adjusted or normalized absolute currency value. Do NOT extract standard Reported PAT, Net Income, or Basic Profit here unless it is expressly labeled as core/adjusted."
    },
    {
        "name": "Normalized Earnings", 
        "type": "Currency", 
        "accept": ["Normalized Earnings"], 
        "reject": ["Adjusted Earnings unless explicitly equated"], 
        "definition": "Earnings calculated by smoothing out fluctuations or one-off items to reflect a 'steady state' profit level. CRITICAL DISTINCTION: This must explicitly represent an adjusted or normalized absolute currency value. Do NOT extract standard Reported PAT, Net Income, or Basic Profit here unless it is expressly labeled as core/adjusted."
    },
    {
        "name": "Core Earnings", 
        "type": "Currency", 
        "accept": ["Core Earnings", "Underlying Profit"], 
        "reject": ["Recurring Earnings", "Net Income", "EBITDA"], 
        "definition": "Profit derived solely from the primary business activities, excluding investment income or secondary operations. CRITICAL DISTINCTION: This must explicitly represent an adjusted or normalized absolute currency value. Do NOT extract standard Reported PAT, Net Income, or Basic Profit here unless it is expressly labeled as core/adjusted."
    },
    {"name": "Recurring Earnings", "type": "Currency", "accept": ["Recurring Earnings"], "reject": ["Implied/Forecasted Earnings", "Adjusted Earnings"], "definition": "Earnings that are expected to repeat in future periods, strictly excluding non-recurring windfalls or losses."},
    {
        "name": "Adjusted EPS", 
        "type": "Currency", 
        "accept": ["Adjusted EPS", "Normalized EPS", "Core EPS"], 
        "reject": ["Basic EPS", "Diluted EPS", "Reported EPS"], 
        "definition": "Earnings Per Share calculated using Adjusted Earnings divided by the weighted average number of shares. CRITICAL DISTINCTION: This is strictly a PER SHARE value. Do NOT extract total corporate absolute currency figures (in millions/billions) here."
    },
    {
        "name": "Normalized EPS", 
        "type": "Currency", 
        "accept": ["Normalized EPS"], 
        "reject": ["Reported EPS", "Basic EPS", "Diluted EPS", "Adjusted EPS"], 
        "definition": "EPS based on normalized earnings to provide a comparable baseline across reporting periods. CRITICAL DISTINCTION: This is strictly a PER SHARE value. Do NOT extract total corporate absolute currency figures (in millions/billions) here."
    },
    {"name": "GAAP One-time Adjustment", "type": "Currency", "accept": ["GAAP one-time adjustment", "One-time GAAP adjustment", "Exceptional GAAP adjustment"], "reject": ["Narrative-only descriptions", "generic exceptional items"], "definition": "Specific numerical adjustments made to reconcile statutory figures to a standardized GAAP presentation."},
    {"name": "GAAP Adjusted", "type": "Currency", "accept": ["GAAP Pro-forma", "GAAP Normalized", "GAAP Adjusted"], "reject": ["Non-GAAP metrics", "plain adjusted figures"], "definition": "Financial figures adjusted within the bounds of GAAP principles rather than using internal management metrics."},
    {
        "name": "EBIT", 
        "type": "Currency", 
        "accept": ["EBIT", "PBIT", "Operating Profit", "Profit before interest and tax"], 
        "reject": ["EBITDA", "PBT", "Profit before tax", "Segment Result", "percentage values"], 
        "definition": "Earnings Before Interest and Taxes. It represents operating profit before financing costs and tax obligations. CRITICAL DISTINCTION: This is the raw statutory absolute currency value. Do NOT extract margins (percentages) or management-adjusted figures here."
    },
    {
        "name": "EBITDA", 
        "type": "Currency", 
        "accept": ["EBITDA", "PBITDA", "Operating EBITDA"], 
        "reject": ["EBIT", "Cash Profit", "PAT", "percentage values"], 
        "definition": "Earnings Before Interest, Taxes, Depreciation, and Amortization. A proxy for operational cash flow before capital reinvestment. CRITICAL DISTINCTION: This is the raw statutory absolute currency value. Do NOT extract margins (percentages) or management-adjusted figures here."
    },
   {
        "name": "Adjusted EBIT", 
        "type": "Currency", 
        "accept": ["Adjusted EBIT", "Normalized EBIT", "EBIT before exceptional items"], 
        "reject": ["Reported EBIT", "plain EBIT", "derived EBIT"], 
        "definition": "EBIT adjusted for non-recurring operational items to show the 'clean' operating performance. CRITICAL DISTINCTION: This must explicitly represent an adjusted absolute currency value. Do NOT extract base reported statutory figures or percentage margins here."
    },
    {
        "name": "Adjusted EBITDA", 
        "type": "Currency", 
        "accept": ["Adjusted EBITDA", "Normalized EBITDA", "Pro-forma EBITDA"], 
        "reject": ["Plain EBITDA", "footnote adjustments"], 
        "definition": "EBITDA further refined to exclude items like restructuring costs, stock-based compensation, or legal settlements. CRITICAL DISTINCTION: This must represent an adjusted absolute currency value. Do NOT extract base reported statutory figures or percentage margins here."
    },
    {"name": "Core Operating Profit", "type": "Currency", "accept": ["Core Operating Profit"], "reject": ["Segment Result", "Operating Profit", "EBITDA"], "definition": "The profit from primary operations only, excluding group-level adjustments or non-core business segments."},
    {
        "name": "EBIT Margin", 
        "type": "Percentage", 
        "accept": ["EBIT Margin", "EBIT Margin %", "Operating Profit Margin", "Operating Profit Margin %", "PBIT Margin"], 
        "reject": ["EBITDA Margin", "Net Profit Margin", "Gross Margin"], 
        "definition": "EBIT expressed as a percentage of total revenue. Measures operational efficiency. CRITICAL DISTINCTION: This is strictly a PERCENTAGE (%) value representing a ratio. Do NOT extract absolute currency amounts or raw profit figures here."
    },
    {
        "name": "EBITDA Margin", 
        "type": "Percentage", 
        "accept": ["EBITDA Margin", "EBITDA Margin %", "PBITDA Margin", "Operating EBITDA Margin"], 
        "reject": ["EBIT Margin", "Net Profit Margin", "Gross Margin"], 
        "definition": "EBITDA as a percentage of revenue. Used to compare profitability across companies with different capital structures. CRITICAL DISTINCTION: This is strictly a PERCENTAGE (%) value representing a ratio. Do NOT extract absolute currency amounts or raw profit figures here."
    },
    {"name": "Base Business Margin", "type": "Percentage", "accept": ["Base Business Margin", "Core Margin", "Base Margin"], "reject": ["Gross Margin", "EBITDA Margin", "Operating Margin"], "definition": "Profit margin specifically for the legacy or core business units, excluding new acquisitions or hyper-growth segments."},
    {
        "name": "Adjusted ROE", 
        "type": "Percentage", 
        "accept": ["Adjusted ROE", "Adjusted Return on Equity"], 
        "reject": ["Reported ROE", "plain ROE", "ROCE"], 
        "definition": "Return on Equity calculated using adjusted net income to show management's efficiency in generating profit from equity. CRITICAL DISTINCTION: This is strictly a PERCENTAGE (%) representing a return ratio. Do NOT extract absolute net income or asset values here."
    },
    {
        "name": "Adjusted ROA", 
        "type": "Percentage", 
        "accept": ["Adjusted ROA", "Adjusted Return on Assets"], 
        "reject": ["Reported ROA", "plain ROA", "RONA", "ROE"], 
        "definition": "Return on Assets using adjusted figures to evaluate asset utilization without the noise of one-time charges. CRITICAL DISTINCTION: This is strictly a PERCENTAGE (%) representing a return ratio. Do NOT extract absolute net income or asset values here."
    },
    {
        "name": "Free Cash Flow (FCF)", 
        "type": "Currency", 
        "accept": ["Free Cash Flow", "FCF"], 
        "reject": ["CFO", "Operating Cash Flow", "FCFE", "FCFF"], 
        "definition": "Operating cash flow minus capital expenditures (CapEx). Represents cash available for distribution or debt reduction. CRITICAL DISTINCTION: Do NOT extract 'Funds From Operations' (FFO) or basic 'Cash from Operations' (CFO) here. Look specifically for the FCF label."
    },
    {"name": "Funds From Operations (FFO)", "type": "Currency", "accept": ["Funds From Operations", "FFO"], "reject": ["AFFO", "Free Cash Flow", "CFO"], "definition": "A measure of cash generated by real estate or investment activities, excluding gains/losses from property sales."},
    {
        "name": "Distributable Cash Flow", 
        "type": "Currency", 
        "accept": ["Distributable Cash Flow", "Cash Available for Distribution", "Distributable Surplus"], 
        "reject": ["Free Cash Flow", "plain Cash Flow"], 
        "definition": "The actual cash available to be paid out as dividends after all necessary capital and debt obligations are met. CRITICAL DISTINCTION: This is the final cash available for dividends. Do NOT extract standard Free Cash Flow (FCF) or Cash from Operations here."
    },
    {"name": "Net Debt", "type": "Currency", "accept": ["Net Debt", "Net Borrowings"], "reject": ["Gross Debt", "Total Debt", "Total Liabilities"], "definition": "Total financial debt minus cash and cash equivalents. Shows the true leverage of the company."},
    {"name": "Net Surplus Cash", "type": "Currency", "accept": ["Net Surplus Cash", "Net Cash Balance", "Net Cash Position", "Net Cash Surplus"], "reject": ["Gross Cash", "FCF", "Cash & Cash Equivalents"], "definition": "The excess cash remaining after all debt and immediate liabilities are theoretically settled."},
    {
        "name": "Constant Currency Revenue", 
        "type": "Currency", 
        "accept": ["Constant Currency Revenue", "FX-neutral Revenue", "Revenue in constant currency terms"], 
        "reject": ["Reported Revenue", "Total Revenue", "plain Revenue"], 
        "definition": "Revenue calculated by eliminating the effect of foreign exchange rate fluctuations. CRITICAL DISTINCTION: This is strictly an ABSOLUTE CURRENCY value. Do NOT extract percentage (%) growth rates here."
    },
    {
        "name": "Constant Currency Revenue Growth", 
        "type": "Percentage", 
        "accept": ["Constant Currency Revenue Growth", "FX-neutral Growth", "Revenue growth in constant currency"], 
        "reject": ["Reported Revenue Growth", "Organic Growth"], 
        "definition": "The percentage increase in revenue adjusted for currency shifts to show underlying volume/price growth. CRITICAL DISTINCTION: This is strictly a PERCENTAGE (%) growth rate. Do NOT extract the absolute constant currency revenue figure here."
    },
    {"name": "Constant Currency Opex", "type": "Currency", "accept": ["Constant Currency Opex", "FX-neutral Opex", "Operating Expenses in constant currency"], "reject": ["Reported Opex", "Total Opex"], "definition": "Operating expenses calculated at fixed exchange rates to evaluate cost management performance."},
    {"name": "ARPU", "type": "Currency", "accept": ["ARPU", "Average Revenue Per User", "Average Revenue Per Subscriber"], "reject": ["Revenue per unit", "Revenue per Employee"], "definition": "Average Revenue Per User. A key metric for subscription or telecommunication businesses."},
    {"name": "Collections", "type": "Currency", "accept": ["Collections", "Sales Collections", "Cash Collections", "Customer Collections"], "reject": ["Revenue", "CFO", "Receipts"], "definition": "Actual cash received from customers during the period, distinct from recognized revenue which may be on credit."},
    {"name": "Pre-sales", "type": "Currency", "accept": ["Pre-sales", "Booking Value pre-revenue", "Contracted Sales", "Pre-launch Sales"], "reject": ["Revenue", "Order Backlog", "Bookings"], "definition": "The value of contracts signed or orders taken for products/services not yet delivered or recognized as revenue."},
    {"name": "Bookings", "type": "Currency", "accept": ["Bookings", "Sales Bookings", "Gross Bookings", "Contracted Value", "Order Value"], "reject": ["Order Backlog", "Revenue", "Pre-sales"], "definition": "Total value of new contracts or orders secured during the period, indicating future revenue pipeline."},
    {"name": "PPOP", "type": "Currency", "accept": ["PPOP", "Pre-Provisioning Operating Profit", "Profit before Provisions"], "reject": ["Net Profit", "Operating Profit (non-banking)", "EBITDA"], "definition": "Operating profit before deducting provisions for bad debts or loan losses. Primarily used in banking."},
    {"name": "Credit Cost ex one-off", "type": "Currency", "accept": ["Credit Cost excluding one-offs", "Credit Cost ex one-off", "Normalized Credit Cost"], "reject": ["Total Provisions", "Gross NPA Provisions"], "definition": "The cost of credit (loan loss provisions) excluding exceptional or non-recurring defaults."},
    {"name": "EVA", "type": "Currency", "accept": ["EVA", "Economic Value Added"], "reject": ["NOPAT", "ROIC", "Economic Profit"], "definition": "The measure of a company's financial performance based on the residual wealth calculated by deducting cost of capital from operating profit."},
    {
        "name": "Cash Earnings", 
        "type": "Currency", 
        "accept": ["Cash Earnings", "Cash Profit"], 
        "reject": ["EBITDA", "CFO", "Operating Cash Flow", "Net Profit"], 
        "definition": "Net income plus non-cash charges like depreciation and amortization. Represents cash-generating capability. CRITICAL DISTINCTION: Do NOT extract standard Net Income, Operating Cash Flow (CFO), or EBITDA here."
    },
    {"name": "Cash Loss", "type": "Currency", "accept": ["Cash Loss numeric value"], "reject": ["Accounting Loss", "Net Loss", "Book Loss"], "definition": "A situation where the actual cash outflows exceed inflows, regardless of non-cash accounting entries."},
    {"name": "Cash Loss Incurrence Status", "type": "Boolean", "accept": ["No cash loss incurred", "Cash loss not incurred", "Company has not incurred cash loss"], "reject": ["Numeric cash loss values"], "definition": "A binary check of whether the auditors or management explicitly state if a cash loss occurred during the period."}
]


# Set of names for cheap membership checks downstream
METRIC_NAMES: frozenset[str] = frozenset(m["name"] for m in METRIC_METADATA)
