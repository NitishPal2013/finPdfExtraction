"""
Pydantic schemas for POC2 (per-metric extraction response).

Schema is intentionally LOOSER than POC1's because:

  - Each call targets ONE metric, not all 37. The prompt constrains
    `metric_target` rather than the schema (so the model can echo names like
    "Free Cash Flow (FCF)" which contain parentheses that Literal types
    handle awkwardly in Gemini's JSON schema).
  - The NULL MANDATE is part of the contract here: `current_year_value` may
    legitimately be `null` when the metric is absent. Caller filters those out.
  - POC1's forbidden-reasoning-phrase gate is intentionally absent here —
    see FORBIDDEN_REASONING_PHRASES below for the why.

Verification response is a tiny separate model.
"""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field


EntityContext = Literal["Consolidated", "Standalone", "Unclear"]
SourceType = Literal["AUDITED_TABLE", "FOOTNOTE", "NARRATIVE"]

# Reference only — POC1 enforces a forbidden-reasoning gate that drops rows
# whose forensic_reasoning_log contains any of these phrases. POC2 keeps the
# list available for future opt-in but does NOT validate against it: the
# per-metric prompt is narrow enough that fabrication via "closest proxy"
# reasoning has been rare in practice, and dropping rows on phrase match
# was costing real positives. Re-enable selectively if drift returns.
FORBIDDEN_REASONING_PHRASES: tuple[str, ...] = (
    "closest proxy", "nearest equivalent", "synonymous with",
    "matches the definition of", "essentially the same as",
    "this is the closest", "as a proxy", "as the closest proxy",
    "approximately equivalent to", "approximate proxy",
    "i will extract", "i will use", "i'll extract", "i'll use",
    "extract the components", "extract the closest",
    "i calculated", "i derived", "i computed",
    "subtract", "subtracted", "subtracting",
    "add back", "adding back", " minus ", " plus ", "= ",
    "while not explicitly", "context suggests",
    "could be interpreted as", "can be interpreted as", "may be interpreted as",
    "this is essentially", "is essentially",
)


class ExtractedMetricPOC2(BaseModel):
    metric_target: str = Field(
        description=(
            "The target metric name as declared in the user turn (e.g. "
            "'EBITDA Margin', 'Free Cash Flow (FCF)'). Copied verbatim from "
            "the dictionary — do not rename or abbreviate."
        )
    )
    forensic_reasoning_log: str = Field(
        default="",
        description=(
            "Rich audit trail (following the structured STEP format in the system prompt). "
            "Must include: exact table/section name, explicit company label or definition quote, "
            "alignment to metric definition (incl. Profit-before components for EBITDA/EBIT), "
            "Consolidated priority justification, verbatim + page/column/year match, and confirmation "
            "of no forbidden derivation or Reject-list hits. MUST NOT contain forbidden reasoning phrases."
        ),
    )
    entity_context: EntityContext = Field(
        default="Unclear",
        description=(
            "Consolidated | Standalone | Unclear. MUST follow the CONSOLIDATED PREFERENCE RULE: "
            "search Consolidated statements first for this metric; return Consolidated if any match found for the metric; "
            "only use Standalone if zero Consolidated disclosures for this exact metric exist in the document."
        ),
    )
    source_type: SourceType = Field(
        default="AUDITED_TABLE",
        description="AUDITED_TABLE | FOOTNOTE | NARRATIVE — physical location.",
    )
    verbatim_source_text: str = Field(
        default="",
        description=(
            "The EXACT complete sentence or table row containing the value. "
            "Copy character-for-character including all brackets."
        ),
    )
    declared_unit: str = Field(
        default="Unstated",
        description=(
            "The scale/unit as printed near the table or value, e.g. "
            "'Rs in Lakhs', 'Millions', '%', 'Unstated'."
        ),
    )
    current_year_value: Optional[str] = Field(
        default=None,
        description=(
            "Raw numerical value (or 'NOT_INCURRED' for the Boolean target) "
            "for the target FY ONLY. Parse brackets as negatives. NULL if the "
            "metric is not present per Accept/Reject rules."
        ),
    )
    page_number: Optional[int] = Field(
        default=None,
        description="Absolute document page number where this was found.",
    )
    table_or_section: Optional[str] = Field(
        default=None,
        description=(
            "Specific table title, note number, or section header where the value was found "
            "(e.g. 'Note 45 - Borrowings', 'MD&A - Financial Highlights table', 'Consolidated Statement of Profit and Loss')."
        ),
    )
    company_definition_quote: Optional[str] = Field(
        default=None,
        description=(
            "If the company explicitly defines or gives a formula for this metric near the value "
            "(e.g. 'Net debt is defined as interest-bearing loans and borrowings less cash and cash equivalents'), quote it verbatim here."
        ),
    )


class Prompt2Response(BaseModel):
    """Top-level response shape — model must return this exact wrapper.
    Each ExtractedMetricPOC2 now supports richer optional fields (table_or_section, company_definition_quote)
    in addition to the enhanced forensic_reasoning_log."""
    extracted_metrics: list[ExtractedMetricPOC2] = Field(
        default_factory=list,
        description=(
            "Zero or more disclosures of the targeted metric in this document. "
            "Empty list (or a single row with `current_year_value: null`) is "
            "the correct output when the metric is absent."
        ),
    )


class VerificationResponse(BaseModel):
    """False-positive audit response for one extracted row."""
    verified: bool = Field(
        description=(
            "True if the extracted figure is genuinely the target metric (per "
            "its definition) and the value matches the document. False if it is "
            "the wrong metric (a confusable sibling) or the value is wrong."
        )
    )
    reason: str = Field(
        default="",
        description="One-sentence justification.",
    )
