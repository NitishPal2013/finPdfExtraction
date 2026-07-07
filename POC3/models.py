"""
Pydantic schemas for POC3: Two-Stage Exhaustive Candidate Extraction & LLM Finalization Layer.

Layer 1 (Candidate Extraction):
  - CandidateMetricPOC3: Captures an individual mention/candidate of a metric across the PDF.
  - CandidateListResponse: Wrapper returning all candidates found for a target metric.

Layer 2 (LLM Finalization):
  - FinalizedMetricPOC3: Captures the selected winner, fallback status, and audit log of rejections.
"""
from __future__ import annotations

from typing import Literal, Optional
from pydantic import BaseModel, Field


EntityContext = Literal["Consolidated", "Standalone", "Unclear"]
SourceType = str


class CandidateMetricPOC3(BaseModel):
    """A single extracted mention or candidate for a target metric from Layer 1."""
    metric_target: str = Field(
        description="The target metric name as declared (e.g., 'EBITDA', 'Net Debt'). Copied verbatim."
    )
    forensic_reasoning_log: str = Field(
        default="",
        description="Detailed notes on where and how this candidate was found in the document."
    )
    entity_context: EntityContext = Field(
        default="Unclear",
        description="Whether this specific candidate figure is under Consolidated or Standalone statements."
    )
    source_type: str = Field(
        default="AUDITED_TABLE",
        description="Describe physical presentation format accurately (e.g., 'AUDITED_TABLE', 'FOOTNOTE', 'NARRATIVE_PARAGRAPH', 'GRAPH', 'BAR_CHART', 'INFOGRAPHIC', 'KPI_HIGHLIGHTS_BOX', 'DIRECTORS_REPORT_TABLE', 'MD&A_CALLOUT', etc.)."
    )
    verbatim_source_text: str = Field(
        default="",
        description="The EXACT complete sentence or table row containing the value. Character-for-character copy."
    )
    declared_unit: str = Field(
        default="Unstated",
        description="The unit/scale printed near the value (e.g., 'Rs in Lakhs', 'Crores', '%', 'Unstated')."
    )
    current_year_value: Optional[str] = Field(
        default=None,
        description="Raw numerical value (or 'NOT_INCURRED') for the target FY ONLY. Null if absent."
    )
    page_number: Optional[int] = Field(
        default=None,
        description="Absolute 1-indexed PDF document page number where this candidate is printed."
    )
    printed_page_number: Optional[str] = Field(
        default=None,
        description="The physical page number printed on the sheet itself (e.g., '81', 'xiv')."
    )
    page_verbatim_proof_above: Optional[str] = Field(
        default=None,
        description="Verbatim text of the row/line immediately preceding verbatim_source_text."
    )
    page_verbatim_proof_below: Optional[str] = Field(
        default=None,
        description="Verbatim text of the row/line immediately following verbatim_source_text."
    )
    absolute_page_confirmation: Optional[bool] = Field(
        default=None,
        description="True if the model explicitly verified physical presence on page_number."
    )
    table_or_section: Optional[str] = Field(
        default=None,
        description="Specific table title, note number, or section header (e.g., 'Note 45 - Borrowings')."
    )
    company_definition_quote: Optional[str] = Field(
        default=None,
        description="Company's own definition or formula quote nearby, if any."
    )


class CandidateListResponse(BaseModel):
    """Top-level response shape for Layer 1 candidate extraction."""
    candidates: list[CandidateMetricPOC3] = Field(
        default_factory=list,
        description="List of all candidate mentions found across the entire document for the target metric."
    )


class FinalizedMetricPOC3(BaseModel):
    """Top-level response shape for Layer 2 LLM finalization and verification."""
    metric_target: str = Field(
        description="The target metric name."
    )
    final_value: Optional[str] = Field(
        default=None,
        description="The winning numerical value (or NOT_INCURRED) for target FY, or null if all candidates rejected."
    )
    winning_candidate: Optional[CandidateMetricPOC3] = Field(
        default=None,
        description="The complete candidate object that was selected as the winner."
    )
    is_standalone_fallback_active: bool = Field(
        default=False,
        description="True if we fell back to Standalone because Consolidated was absent across all candidates."
    )
    rejection_audit_log: list[str] = Field(
        default_factory=list,
        description="Detailed explanation for each candidate evaluated: why it was accepted as winner or rejected."
    )
    final_forensic_summary: str = Field(
        default="",
        description="Overall summary of the finalization decision and proof verification for this metric."
    )
