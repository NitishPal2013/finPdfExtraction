"""
Pydantic models for prompt_template (37-target forensic sweeper) structured output.

Mirrors the JSON schema declared at the bottom of prompt_template in POC1/prompt.py.
Field descriptions are intentionally verbose because Gemini reads them as part of
the response schema and they directly influence extraction quality.

Field order matters: Gemini's autoregressive emission tends to follow the schema
order. `literal_label_quote` is FIRST so the model commits to a verbatim printed
label before committing to a target — making it physically harder to write a
reasoning log that says "no, this metric is not present" while still emitting
the row with a substituted value.
"""
from typing import Literal, Optional
from pydantic import BaseModel, Field, field_validator, model_validator


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


# ---------------------------------------------------------------------------
# Value-format taxonomy. Used by the model_validator below to gate format
# mismatches: a percentage-only target like EBIT Margin must never carry a
# currency value; a currency-only target like EBIT must never carry a `%`.
# ---------------------------------------------------------------------------

PERCENTAGE_TARGETS: frozenset[str] = frozenset({
    "EBIT Margin",
    "EBITDA Margin",
    "Base Business Margin",
    "Adjusted ROE",
    "Adjusted ROA",
    "Constant Currency Revenue Growth",
})

# Cash Loss Incurrence Status is the ONE target that carries a string literal.
STRING_LITERAL_TARGETS: frozenset[str] = frozenset({
    "Cash Loss Incurrence Status",
})

# All other targets require a currency-style numeric value.


# ---------------------------------------------------------------------------
# Forbidden reasoning phrases. The prompt also lists these — keep the two
# lists in sync. Any case-insensitive substring match in the reasoning log
# means the row is fabricated and must be dropped.
#
# Categories represented:
#   - "closest proxy" reasoning ("nearest equivalent", "synonymous with", ...)
#   - explicit substitution intent ("I will extract X as", "I will use X instead")
#   - math contamination ("derived", "calculated", "minus", "plus", "subtract", ...)
#   - speculative hedging ("while not explicitly", "context suggests", ...)
# ---------------------------------------------------------------------------

FORBIDDEN_REASONING_PHRASES: tuple[str, ...] = (
    # closest-proxy / synonym substitution
    "closest proxy",
    "nearest equivalent",
    "synonymous with",
    "matches the definition of",
    "essentially the same as",
    "this is the closest",
    "as a proxy",
    "as the closest proxy",
    "approximately equivalent to",
    "approximate proxy",
    # explicit substitution intent
    "i will extract",
    "i will use",
    "i'll extract",
    "i'll use",
    "extract the components",
    "extract the closest",
    # math contamination
    "i calculated",
    "i derived",
    "i computed",
    "subtract",
    "subtracted",
    "subtracting",
    "add back",
    "adding back",
    " minus ",
    " plus ",
    "= ",
    # speculative hedging
    "while not explicitly",
    "context suggests",
    "could be interpreted as",
    "can be interpreted as",
    "may be interpreted as",
    "this is essentially",
    "is essentially",
)


# ---------------------------------------------------------------------------
# Null-value sentinels rejected by the value validator. These are the
# placeholders the model emits when its reasoning concludes "no extraction"
# but the schema still demands a string.
# ---------------------------------------------------------------------------

NULL_VALUE_SENTINELS: frozenset[str] = frozenset({
    "",
    "-",
    "—",
    "–",
    "n/a",
    "na",
    "not_found",
    "not found",
    "null",
    "none",
    "nil",
})


def _looks_numeric(value: str) -> bool:
    """True if `value` parses as a number after stripping common scaffolding.

    Tolerates: commas as thousand separators, leading/trailing spaces, a
    single trailing `%`, leading currency symbols (₹, $, €, £), parentheses
    indicating negatives, and a leading minus sign.
    """
    if not value:
        return False
    cleaned = value.strip()
    # Strip wrapping parentheses (negative convention)
    if cleaned.startswith("(") and cleaned.endswith(")"):
        cleaned = cleaned[1:-1].strip()
    # Strip currency prefixes
    for prefix in ("₹", "$", "€", "£", "Rs.", "Rs", "INR", "USD"):
        if cleaned.startswith(prefix):
            cleaned = cleaned[len(prefix):].strip()
            break
    # Strip trailing percent
    cleaned = cleaned.rstrip("%").strip()
    # Strip commas + whitespace
    cleaned = cleaned.replace(",", "").replace(" ", "")
    if not cleaned:
        return False
    try:
        float(cleaned)
        return True
    except ValueError:
        return False


class ExtractedMetric(BaseModel):
    # Field order is significant — see module docstring.

    literal_label_quote: str = Field(
        description=(
            "STEP 1 (gate): Copy the EXACT printed metric name from the page — just the "
            "label words, NOT the value. Examples: 'EBITDA', 'Net Debt', 'PBDIT', 'EBIT "
            "Margin', 'Operating Profit Margin', 'Adjusted EBITDA'. If no label on the "
            "page semantically denotes the target metric (per its First-Principles "
            "Definition) — OR if the label is on the target's Reject list — STOP and do "
            "not emit any further keys for this candidate row."
        )
    )
    metric_target: MetricTarget = Field(
        description=(
            "STEP 2: The dictionary target whose First-Principles Definition matches the "
            "meaning of literal_label_quote. The Common Printed Variants list illustrates "
            "frequent Indian-PDF phrasings but is NOT exhaustive — use your financial "
            "training to recognize semantic equivalents. The Reject list, however, is "
            "closed: never tag a Reject-list label (or its semantic equivalent) as this "
            "target. Copied verbatim from the 37-name dictionary. Do not rename, "
            "abbreviate, or invent."
        )
    )
    verbatim_source_text: str = Field(
        description=(
            "STEP 3: The EXACT complete sentence or table row containing the value. "
            "Must include the literal_label_quote as a substring. Copy character-for-"
            "character including all brackets."
        )
    )
    forensic_reasoning_log: str = Field(
        description=(
            "STEP 4: Prove (a) literal_label_quote denotes metric_target per its "
            "First-Principles Definition AND is not on metric_target's Reject list, "
            "(b) the value matches the target's Value Format (currency vs percentage), "
            "(c) NO forbidden phrases are used (no 'closest proxy', no 'derived', no "
            "'subtract', no 'I will use X instead'). One concise paragraph — this is "
            "the audit trail."
        )
    )
    entity_context: EntityContext = Field(
        description=(
            "STEP 5: Whether this disclosure is from Consolidated group statements, "
            "Standalone (Company) statements, or Unclear from the surrounding text. "
            "Track the most recent section header ('Consolidated Financial Statements' "
            "or 'Standalone Financial Statements'). 'Unclear' is the correct answer "
            "when no section header is visible — never default to Consolidated."
        )
    )
    source_type: SourceType = Field(
        description=(
            "STEP 6: Where the value was physically found — AUDITED_TABLE (formal P&L, "
            "Balance Sheet, Cash Flow), FOOTNOTE (Notes to Accounts), or NARRATIVE "
            "(Chairman's Letter, MD&A, Highlights, infographic boxes, bullet points)."
        )
    )
    surrounding_context: str = Field(
        description=(
            "STEP 7: The paragraph or table header immediately preceding the finding. "
            "Provides enough signal for the merge step to disambiguate duplicates "
            "across overlap."
        )
    )
    declared_unit: str = Field(
        description=(
            "STEP 8: The scale/unit of the figure as printed near the table or value, "
            "e.g. '₹ in Lakhs', 'Millions', '%', 'Unstated'. Do not infer — read "
            "the document."
        )
    )
    current_year_value: str = Field(
        description=(
            "STEP 9: The raw numerical value from the verbatim text for the target "
            "FY ONLY. Parse brackets as negatives (e.g. '(4,500)' → '-4500'). A dash "
            "cell becomes '0'. NEVER null/None/empty/'—'/'N/A'/'NOT_FOUND'. The ONLY "
            "string-literal exception is `Cash Loss Incurrence Status`, whose value "
            "is exactly 'NOT_INCURRED'. If you cannot produce a real number for any "
            "other target, do not emit the row at all."
        )
    )
    page_number: int = Field(
        description=(
            "The absolute document page number where this was found (use the page "
            "number provided in the chunk instruction, not a printed footer that "
            "may differ)."
        )
    )

    # ------------------------------------------------------------------
    # Validators
    # ------------------------------------------------------------------

    @field_validator("forensic_reasoning_log")
    @classmethod
    def _no_forbidden_phrases(cls, v: str) -> str:
        lowered = v.lower()
        for phrase in FORBIDDEN_REASONING_PHRASES:
            if phrase in lowered:
                raise ValueError(
                    f"forensic_reasoning_log contains forbidden phrase {phrase!r}; "
                    "row is fabricated by substitution / proxy / math reasoning"
                )
        return v

    @model_validator(mode="after")
    def _value_and_label_gates(self) -> "ExtractedMetric":
        target = self.metric_target
        value = (self.current_year_value or "").strip()

        # Gate A — string-literal targets (Cash Loss Incurrence Status)
        if target in STRING_LITERAL_TARGETS:
            if value != "NOT_INCURRED":
                raise ValueError(
                    f"{target} must carry value 'NOT_INCURRED'; got {value!r}"
                )
        else:
            # Gate B — null sentinels rejected for every numeric target
            if value.lower() in NULL_VALUE_SENTINELS:
                raise ValueError(
                    f"current_year_value {value!r} is a null/empty sentinel — row "
                    "must be omitted, not emitted with a placeholder"
                )
            # Gate C — must look like a number
            if not _looks_numeric(value):
                raise ValueError(
                    f"current_year_value {value!r} for {target} does not parse as "
                    "a number; row would be a hallucination"
                )

        # Gate D — value-format mismatch
        ends_with_percent = value.rstrip().endswith("%")
        if target in PERCENTAGE_TARGETS:
            if not ends_with_percent:
                raise ValueError(
                    f"{target} requires a percentage value (e.g. '12.6%'); got "
                    f"{value!r}"
                )
        elif target not in STRING_LITERAL_TARGETS:
            if ends_with_percent:
                raise ValueError(
                    f"{target} requires a currency value (no % suffix); got "
                    f"{value!r} — likely a margin row mistagged as a level"
                )

        # Gate E — literal_label_quote must actually appear in verbatim_source_text
        quote = (self.literal_label_quote or "").strip().lower()
        verbatim_lc = (self.verbatim_source_text or "").lower()
        if quote and quote not in verbatim_lc:
            raise ValueError(
                f"literal_label_quote {self.literal_label_quote!r} is not a "
                "substring of verbatim_source_text — quote is fabricated"
            )

        return self


class Prompt15Response(BaseModel):
    extracted_metrics: list[ExtractedMetric] = Field(
        default_factory=list,
        description=(
            "Every disclosure in this chunk that matches one of the 37 Metric Dictionary "
            "principles. Return an empty array if the chunk contains nothing relevant — "
            "do not invent matches."
        ),
    )
