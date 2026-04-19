"""
Pydantic models for prompt_template (37-target forensic sweeper) structured output.

Mirrors the JSON schema declared at the bottom of prompt_template in
src/prompts/AnalyzeSection.py. Field descriptions are intentionally
verbose because Gemini reads them as part of the response schema and
they directly influence extraction quality.
"""
from typing import Literal, Optional
from pydantic import BaseModel, Field


EntityContext = Literal["Consolidated", "Standalone", "Unclear"]
SourceType = Literal["AUDITED_TABLE", "FOOTNOTE", "NARRATIVE"]


# Exact Target names verbatim from prompt_template (CLASS A through CLASS G, 37 total).
# Using Literal constrains Gemini to pick only from these strings — no typos,
# no invented names, no drift across windows.
MetricTarget = Literal[
    # CLASS A: MODIFIED & ADJUSTED PROFITABILITY (9)
    "Adjusted Revenue",
    "Adjusted Earnings",
    "Normalized Earnings",
    "Core Earnings",
    "Recurring Earnings",
    "Adjusted EPS",
    "Normalized EPS",
    "GAAP One-time Adjustment",
    "GAAP Adjusted",
    # CLASS B: STATUTORY & OPERATIONAL PROFITABILITY (5)
    "EBIT",
    "EBITDA",
    "Adjusted EBIT",
    "Adjusted EBITDA",
    "Core Operating Profit",
    # CLASS C: MARGINS & RATIOS (5)
    "EBIT Margin",
    "EBITDA Margin",
    "Base Business Margin",
    "Adjusted ROE",
    "Adjusted ROA",
    # CLASS D: LIQUIDITY, CASH FLOW & DEBT (5)
    "Free Cash Flow (FCF)",
    "Funds From Operations (FFO)",
    "Distributable Cash Flow",
    "Net Debt",
    "Net Surplus Cash",
    # CLASS E: FOREX MODIFIED METRICS (3)
    "Constant Currency Revenue",
    "Constant Currency Revenue Growth",
    "Constant Currency Opex",
    # CLASS F: SECTOR-SPECIFIC METRICS (7)
    "ARPU",
    "Collections",
    "Pre-sales",
    "Bookings",
    "PPOP",
    "Credit Cost ex one-off",
    "EVA",
    # CLASS G: STATUTORY AUDITOR (CARO) DISCLOSURES (3)
    "Cash Earnings",
    "Cash Loss",
    "Cash Loss Incurrence Status",
]


class ExtractedMetric(BaseModel):
    metric_target: MetricTarget = Field(
        description=(
            "The exact Target name this extraction matches, copied verbatim from the 37-name "
            "Metric Dictionary. Do not rename, abbreviate, or invent."
        )
    )
    forensic_reasoning_log: str = Field(
        description=(
            "STEP 1: Prove how the Semantic Principle is met. Which column did you read? "
            "Why does the label match the Accept list and dodge the Reject list? "
            "One concise paragraph — this is the audit trail."
        )
    )
    entity_context: EntityContext = Field(
        description=(
            "STEP 2: Whether this disclosure is from Consolidated group statements, Standalone "
            "(Company) statements, or Unclear from the surrounding text. Read page headers / "
            "section titles. 'Unclear' is a valid answer when there is no signal."
        )
    )
    source_type: SourceType = Field(
        description=(
            "STEP 3: Where the value was physically found — AUDITED_TABLE (formal P&L, Balance "
            "Sheet, Cash Flow), FOOTNOTE (Notes to Accounts), or NARRATIVE (Chairman's Letter, "
            "MD&A, Highlights, bullet points)."
        )
    )
    verbatim_source_text: str = Field(
        description=(
            "STEP 4: The EXACT, complete sentence or table row where the metric was found, "
            "copied character-for-character including all brackets. This is the anchor the merge "
            "step uses to dedupe overlapping-window hits — precision matters."
        )
    )
    surrounding_context: str = Field(
        description=(
            "STEP 5: The paragraph or table header immediately preceding the finding. "
            "Provides enough signal for the merge step to disambiguate duplicates across overlap."
        )
    )
    declared_unit: str = Field(
        description=(
            "STEP 6: The scale/unit of the figure as printed near the table or value, e.g. "
            "'₹ in Lakhs', 'Millions', '%', 'Unstated'. Do not infer — read the document."
        )
    )
    current_year_value: Optional[str] = Field(
        default=None,
        description=(
            "STEP 7: The raw numerical value from the verbatim text for the target FY ONLY. "
            "Parse brackets as negatives (e.g. '(4,500)' → '-4500'). A dash cell becomes '0'. "
            "Return null ONLY for EVA when it is mentioned by name but no number is printed."
        )
    )
    page_number: int = Field(
        description=(
            "The absolute document page number where this was found (use the page number "
            "provided in the chunk instruction, not a printed footer that may differ)."
        )
    )


class Prompt15Response(BaseModel):
    extracted_metrics: list[ExtractedMetric] = Field(
        default_factory=list,
        description=(
            "Every disclosure in this chunk that matches one of the 37 Metric Dictionary "
            "principles. Return an empty array if the chunk contains nothing relevant — "
            "do not invent matches."
        ),
    )
