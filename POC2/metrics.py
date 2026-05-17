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


METRIC_METADATA: list[MetricDef] = [
    # CLASS A — Modified & Adjusted Profitability
    {"name": "Adjusted Revenue", "type": "Currency",
     "accept": ["Adjusted Revenue", "Normalized Revenue", "Pro-forma Revenue",
                "Core Revenue", "Non-GAAP Revenue", "Underlying Revenue"],
     "reject": ["Reported Revenue", "Total Revenue", "Revenue from Operations",
                "Net Revenue", "Sales", "Turnover"]},
    {"name": "Adjusted Earnings", "type": "Currency",
     "accept": ["Adjusted PAT", "Normalized PAT", "Underlying Earnings",
                "Core PAT", "Adjusted Net Profit", "Adjusted Earnings"],
     "reject": ["PAT before exceptional items", "Reported PAT", "Net Profit",
                "Net Income", "Profit for the year"]},
    {"name": "Normalized Earnings", "type": "Currency",
     "accept": ["Normalized Earnings", "Normalized Net Income",
                "Normalized Profit"],
     "reject": ["Adjusted Earnings unless explicitly equated",
                "Reported Earnings", "PAT"]},
    {"name": "Core Earnings", "type": "Currency",
     "accept": ["Core Earnings", "Core Profit", "Underlying Profit",
                "Core Net Income"],
     "reject": ["Recurring Earnings", "Net Income", "EBITDA",
                "Operating Profit"]},
    {"name": "Recurring Earnings", "type": "Currency",
     "accept": ["Recurring Earnings", "Recurring Net Income",
                "Recurring Profit"],
     "reject": ["Implied/Forecasted Earnings", "Adjusted Earnings",
                "Core Earnings"]},
    {"name": "Adjusted EPS", "type": "Currency",
     "accept": ["Adjusted EPS", "Normalized EPS", "Core EPS",
                "Adjusted Earnings Per Share", "Underlying EPS"],
     "reject": ["Basic EPS", "Diluted EPS", "Reported EPS",
                "Earnings per share without qualifier"]},
    {"name": "Normalized EPS", "type": "Currency",
     "accept": ["Normalized EPS", "Normalized Earnings Per Share"],
     "reject": ["Reported EPS", "Basic EPS", "Diluted EPS", "Adjusted EPS"]},
    {"name": "GAAP One-time Adjustment", "type": "Currency",
     "accept": ["GAAP one-time adjustment", "One-time GAAP adjustment",
                "Exceptional GAAP adjustment", "Non-GAAP adjustment in bridge"],
     "reject": ["Narrative-only descriptions", "generic exceptional items",
                "Exceptional Items P&L line", "Note 48 - Exceptional Items"]},
    {"name": "GAAP Adjusted", "type": "Currency",
     "accept": ["GAAP Pro-forma", "GAAP Normalized", "GAAP Adjusted"],
     "reject": ["Non-GAAP metrics", "plain adjusted figures"]},

    # CLASS B — Statutory & Operational Profitability
    {"name": "EBIT", "type": "Currency",
     "accept": ["EBIT", "PBIT", "Operating Profit",
                "Profit before interest and tax",
                "Profit before finance cost and tax"],
     "reject": ["EBITDA", "PBT", "Profit before tax", "Segment Result",
                "PBDIT", "PBIDT", "Cash Profit", "any percentage value"]},
    {"name": "EBITDA", "type": "Currency",
     "accept": ["EBITDA", "PBITDA", "PBDIT", "PBIDT", "Operating EBITDA",
                "Earnings before interest, taxation, depreciation and amortization",
                "Profit before Depreciation, Interest and Tax"],
     "reject": ["EBIT", "Cash Profit", "PAT", "Operating profit before working capital changes",
                "any percentage value", "Adjusted EBITDA"]},
    {"name": "Adjusted EBIT", "type": "Currency",
     "accept": ["Adjusted EBIT", "Normalized EBIT", "Underlying EBIT",
                "EBIT before exceptional items"],
     "reject": ["Reported EBIT", "plain EBIT", "derived EBIT",
                "any percentage value"]},
    {"name": "Adjusted EBITDA", "type": "Currency",
     "accept": ["Adjusted EBITDA", "Normalized EBITDA", "Pro-forma EBITDA",
                "Core EBITDA", "Underlying EBITDA"],
     "reject": ["Plain EBITDA", "Operating EBITDA without qualifier",
                "Segment-qualified Adjusted EBITDA (e.g. Food delivery Adjusted EBITDA)"]},
    {"name": "Core Operating Profit", "type": "Currency",
     "accept": ["Core Operating Profit"],
     "reject": ["Segment Result", "Operating Profit", "EBITDA"]},

    # CLASS C — Margins & Ratios (must be %)
    {"name": "EBIT Margin", "type": "Percentage",
     "accept": ["EBIT Margin", "EBIT Margin %", "Operating Profit Margin",
                "Operating Profit Margin %", "PBIT Margin", "EBIT %"],
     "reject": ["EBITDA Margin", "Net Profit Margin", "Gross Margin",
                "ROCE", "Return on Capital Employed", "ROE", "ROA",
                "any currency value"]},
    {"name": "EBITDA Margin", "type": "Percentage",
     "accept": ["EBITDA Margin", "EBITDA Margin %", "PBDIT Margin",
                "PBIDT Margin", "Operating EBITDA Margin", "EBIDTA Margin"],
     "reject": ["EBIT Margin", "Net Profit Margin", "Gross Margin",
                "Adjusted EBITDA Margin",
                "Segment-qualified EBITDA Margin (e.g. Food delivery EBITDA Margin)",
                "any currency value"]},
    {"name": "Base Business Margin", "type": "Percentage",
     "accept": ["Base Business Margin", "Core Margin", "Base Margin"],
     "reject": ["Gross Margin", "EBITDA Margin", "Operating Margin",
                "Net Margin", "any currency value"]},
    {"name": "Adjusted ROE", "type": "Percentage",
     "accept": ["Adjusted ROE", "Adjusted Return on Equity", "Normalized ROE"],
     "reject": ["Reported ROE", "plain ROE", "ROCE",
                "Return on Net Worth without qualifier", "any currency value"]},
    {"name": "Adjusted ROA", "type": "Percentage",
     "accept": ["Adjusted ROA", "Adjusted Return on Assets"],
     "reject": ["Reported ROA", "plain ROA", "RONA", "ROE",
                "any currency value"]},

    # CLASS D — Liquidity, Cash Flow & Debt
    {"name": "Free Cash Flow (FCF)", "type": "Currency",
     "accept": ["Free Cash Flow", "FCF"],
     "reject": ["CFO", "Operating Cash Flow", "FCFE", "FCFF",
                "Cash Flow from Operations"]},
    {"name": "Funds From Operations (FFO)", "type": "Currency",
     "accept": ["Funds From Operations", "FFO"],
     "reject": ["AFFO", "Free Cash Flow", "CFO"]},
    {"name": "Distributable Cash Flow", "type": "Currency",
     "accept": ["Distributable Cash Flow", "Cash Available for Distribution",
                "Distributable Surplus"],
     "reject": ["Free Cash Flow", "plain Cash Flow"]},
    {"name": "Net Debt", "type": "Currency",
     "accept": ["Net Debt", "Net Borrowings"],
     "reject": ["Gross Debt", "Total Debt", "Total Liabilities",
                "Total Borrowings"]},
    {"name": "Net Surplus Cash", "type": "Currency",
     "accept": ["Net Surplus Cash", "Net Cash Balance",
                "Net Cash Position", "Net Cash Surplus"],
     "reject": ["Gross Cash", "FCF", "Cash & Cash Equivalents"]},

    # CLASS E — Forex Modified Metrics
    {"name": "Constant Currency Revenue", "type": "Currency",
     "accept": ["Constant Currency Revenue", "FX-neutral Revenue",
                "Revenue in constant currency terms"],
     "reject": ["Reported Revenue", "Total Revenue", "plain Revenue"]},
    {"name": "Constant Currency Revenue Growth", "type": "Percentage",
     "accept": ["Constant Currency Revenue Growth", "FX-neutral Growth",
                "Revenue growth in constant currency"],
     "reject": ["Reported Revenue Growth", "Organic Growth",
                "any currency value"]},
    {"name": "Constant Currency Opex", "type": "Currency",
     "accept": ["Constant Currency Opex", "FX-neutral Opex",
                "Operating Expenses in constant currency"],
     "reject": ["Reported Opex", "Total Opex"]},

    # CLASS F — Sector-specific
    {"name": "ARPU", "type": "Currency",
     "accept": ["ARPU", "Average Revenue Per User",
                "Average Revenue Per Subscriber"],
     "reject": ["Revenue per unit", "Revenue per Employee"]},
    {"name": "Collections", "type": "Currency",
     "accept": ["Collections", "Sales Collections", "Cash Collections",
                "Customer Collections"],
     "reject": ["Revenue", "CFO", "Receipts"]},
    {"name": "Pre-sales", "type": "Currency",
     "accept": ["Pre-sales", "Booking Value pre-revenue",
                "Contracted Sales", "Pre-launch Sales"],
     "reject": ["Revenue", "Order Backlog", "Bookings"]},
    {"name": "Bookings", "type": "Currency",
     "accept": ["Bookings", "Sales Bookings", "Gross Bookings",
                "Contracted Value", "Order Value"],
     "reject": ["Order Backlog", "Revenue", "Pre-sales"]},
    {"name": "PPOP", "type": "Currency",
     "accept": ["PPOP", "Pre-Provisioning Operating Profit",
                "Profit before Provisions"],
     "reject": ["Net Profit", "Operating Profit (non-banking)", "EBITDA"]},
    {"name": "Credit Cost ex one-off", "type": "Currency",
     "accept": ["Credit Cost excluding one-offs", "Credit Cost ex one-off",
                "Normalized Credit Cost"],
     "reject": ["Total Provisions", "Gross NPA Provisions"]},
    {"name": "EVA", "type": "Currency",
     "accept": ["EVA", "Economic Value Added"],
     "reject": ["NOPAT", "ROIC", "Economic Profit"]},

    # CLASS G — Statutory Auditor (CARO) disclosures
    {"name": "Cash Earnings", "type": "Currency",
     "accept": ["Cash Earnings", "Cash Profit"],
     "reject": ["EBITDA", "CFO", "Operating Cash Flow", "Net Profit"]},
    {"name": "Cash Loss", "type": "Currency",
     "accept": ["Cash Loss numeric value"],
     "reject": ["Accounting Loss", "Net Loss", "Book Loss"]},
    {"name": "Cash Loss Incurrence Status", "type": "Boolean",
     "accept": ["No cash loss incurred", "Cash loss not incurred",
                "Company has not incurred cash loss"],
     "reject": ["Numeric cash loss values"]},
]


# Set of names for cheap membership checks downstream
METRIC_NAMES: frozenset[str] = frozenset(m["name"] for m in METRIC_METADATA)
