"""
Prompts for POC3: Two-Stage Exhaustive Candidate Extraction & LLM Finalization Layer.

Layer 1 (Candidate Extraction):
  - BASE_SYSTEM_INSTRUCTION: Pinned to the Gemini File Cache. Instructs model to act as an exhaustive scanner without discarding mentions prematurely, using step-by-step section traversal and flexible source types.
  - build_candidate_extraction_prompt: Per-metric call instructing the model to harvest all mentions across the PDF.

Layer 2 (LLM Finalization):
  - build_finalization_prompt: Passes harvested candidates to Gemini to verify page proofs, enforce Consolidated preference, rank by Audited Table > Notes > Narrative/Charts, and output the winner with an audit trail.
"""
from __future__ import annotations

import json
from POC3.metrics import MetricDef


COMPANY_PLACEHOLDER = "[INSERT_COMPANY_NAME]"
FY_PLACEHOLDER = "[INSERT_TARGET_FY_YEAR]"


BASE_SYSTEM_INSTRUCTION = """### SYSTEM ROLE: EXHAUSTIVE FINANCIAL CANDIDATE HARVESTING ENGINE (LAYER 1)
You are an elite, thorough financial data harvesting engine.
Your target company is: **[INSERT_COMPANY_NAME]**
Your target reporting period is: **[INSERT_TARGET_FY_YEAR]** (e.g., FY24 / March 31, 2024).

Your sole purpose in Layer 1 is to perform an **Exhaustive Candidate Search** across the entire document for the target metric requested in each turn. Unlike standard extractors that prematurely filter and pick a single winner, your job here is to **HARVEST AND RETURN ALL POSSIBLE MENTIONS / CANDIDATES** of the target metric across the report.

### LAYER 1 HARVESTING RULES:
1. **NO PREMATURE REJECTION BY SCOPE OR FORMAT:** If the metric is disclosed in multiple locations (e.g., in Standalone Statement of Profit and Loss, Consolidated Statement of Cash Flows, MD&A narrative, Infographics, Graphs, Bar Charts, and Note 45), you must capture and return **ALL of them** in the `candidates` array! Do not discard Standalone mentions just because Consolidated mentions exist—capture both so Layer 2 can audit them.
2. **ZERO-TOLERANCE ON ARITHMETIC:** You must never calculate or derive numbers. Every candidate value must be explicitly printed on the page for the target FY column.
3. **MANDATORY PHYSICAL PAGE PROOFS:** To prove the physical location of each candidate, you must:
   - Record the exact 1-indexed PDF document `page_number`.
   - Record the printed page number on the sheet (`printed_page_number`).
   - Capture the exact verbatim printed text of the line immediately ABOVE the match (`page_verbatim_proof_above`).
   - Capture the exact verbatim printed text of the line immediately BELOW the match (`page_verbatim_proof_below`).
   - Set `absolute_page_confirmation` to true.
4. **ENTITY CONTEXT TAGGING:** For every candidate, tag `entity_context` as `"Consolidated"`, `"Standalone"`, or `"Unclear"`.
5. **SOURCE TYPE TAGGING:** Tag `source_type` with an accurate description of the presentation format where you found the item—such as `AUDITED_TABLE`, `FOOTNOTE`, `NARRATIVE_PARAGRAPH`, `GRAPH`, `BAR_CHART`, `INFOGRAPHIC`, `KPI_HIGHLIGHTS_BOX`, `DIRECTORS_REPORT_TABLE`, `MD&A_CALLOUT`, etc. Be descriptive and accurate; disclosures can appear anywhere in the report!
6. **STEP-BY-STEP SECTION TRAVERSAL STRATEGY:** To ensure exhaustive recall without missing anything across the document:
   - **Step 1:** Check the Table of Contents (TOC) if present, or scan the major section headings of the report to map out where financial performance, operational metrics, graphs, accounting policies, and statements are located.
   - **Step 2:** Systematically iterate through each relevant section one by one (e.g., Highlights & Infographics -> Directors' Report -> Management Discussion & Analysis -> Consolidated Financial Statements -> Standalone Financial Statements -> Notes to Accounts).
   - **Step 3:** For each section traversed, search for any trace or mention of the target metric or its synonyms, capturing all candidates found. Record your traversal notes in `forensic_reasoning_log`.
7. **THE NULL DEFAULT:** If after an exhaustive search from start to finish you find zero mentions of the metric or its accepted synonyms, return an empty `candidates` list.

### JSON SCHEMA
```json
{
  "candidates": [
    {
      "metric_target": "Exact name of target metric",
      "forensic_reasoning_log": "Detailed notes on step-by-step section traversal and where/how this candidate was found",
      "entity_context": "Consolidated | Standalone | Unclear",
      "source_type": "AUDITED_TABLE | FOOTNOTE | NARRATIVE_PARAGRAPH | GRAPH | BAR_CHART | INFOGRAPHIC | KPI_HIGHLIGHTS_BOX | etc.",
      "verbatim_source_text": "Exact complete row/sentence/label containing the value",
      "declared_unit": "Rs in Lakhs | Crores | % | Unstated",
      "current_year_value": "raw number as string (or NOT_INCURRED)",
      "page_number": 0,
      "printed_page_number": "printed sheet number e.g. '81'",
      "page_verbatim_proof_above": "exact text of line immediately above",
      "page_verbatim_proof_below": "exact text of line immediately below",
      "absolute_page_confirmation": true,
      "table_or_section": "table title, note number, chart title, or section header",
      "company_definition_quote": "company definition/formula quote nearby if any"
    }
  ]
}
```
CRITICAL OUTPUT RULE: Return ONLY valid JSON parseable by `json.loads()`.
"""


def build_system_instruction(company_display: str, fy_year: str) -> str:
    """Return BASE_SYSTEM_INSTRUCTION with placeholders substituted."""
    return (
        BASE_SYSTEM_INSTRUCTION
        .replace(COMPANY_PLACEHOLDER, company_display)
        .replace(FY_PLACEHOLDER, fy_year)
    )


def build_candidate_extraction_prompt(metric: MetricDef) -> str:
    """Per-metric prompt for Layer 1 candidate harvesting."""
    return f"""EXHAUSTIVE CANDIDATE HARVESTING TASK (LAYER 1):

TARGET METRIC: **{metric['name']}**
DEFINITION: {metric['definition']}
SEEK TERMS: {', '.join(metric['accept'])}
DIFFERENTIATE FROM (REJECT TERMS): {', '.join(metric['reject'])}

INSTRUCTIONS:
1. Search the ENTIRE PDF from cover to cover using a **step-by-step section traversal**: check the Table of Contents (TOC) or document structure first, then systematically iterate through every section (Highlights, Graphs/Charts, MD&A, Consolidated Statements, Standalone Statements, Notes to Accounts, Auditor's Report).
2. Harvest every valid mention or candidate figure for **{metric['name']}** for the target FY.
3. Do NOT discard candidates based on Consolidated vs Standalone preference or presentation format (table, graph, chart, infographic, footnote, narrative)—return the full candidate pool so our Layer 2 audit engine can evaluate all of them.
4. Ensure every candidate includes its exact verbatim text, value, entity_context, descriptive source_type, page_number, and the mandatory physical line proofs (`page_verbatim_proof_above` and `page_verbatim_proof_below`). Record your step-by-step sectional findings in `forensic_reasoning_log`.

If no candidates exist anywhere in the document, return `{{"candidates": []}}`.
"""


def build_finalization_prompt(metric: MetricDef, candidates: list[dict]) -> str:
    """Prompt for Layer 2 LLM finalization and verification."""
    candidates_json = json.dumps(candidates, indent=2)
    return f"""AGENTIC FINALIZATION & AUDIT TASK (LAYER 2 - PRECISION SELECTION):

You are an elite financial verification and finalization auditor.
We have harvested {len(candidates)} candidate(s) for the target metric: **{metric['name']}**.

METRIC DEFINITION:
{metric['definition']}

SEEK TERMS: {', '.join(metric['accept'])}
REJECT TERMS: {', '.join(metric['reject'])}

HARVESTED CANDIDATES POOL:
{candidates_json}

YOUR TASK — EXECUTE THESE 3 SELECTION STEPS IN ORDER:

STEP 1: PHYSICAL PAGE PROOF VERIFICATION (STRICT PRE-FILTER)
Inspect each candidate's `page_verbatim_proof_above`, `page_verbatim_proof_below`, `printed_page_number`, and `verbatim_source_text`.
- If the surrounding proof lines or verbatim text indicate a hallucination, mismatch, or page-attribution error, IMMEDIATELY REJECT the candidate!
- Record the rejection in `rejection_audit_log`: e.g., "[REJECTED Candidate on Page X]: Failed physical page proof verification."

STEP 2: ENTITY SCOPE PREFERENCE (CONSOLIDATED PREFERENCE RULE)
Look at the surviving candidates:
- If ANY valid candidate is tagged as `entity_context: "Consolidated"`, you MUST REJECT all `Standalone` candidates! The group-level Consolidated figure always takes precedence.
- Record the rejection in `rejection_audit_log`: e.g., "[REJECTED Candidate on Page Y]: Standalone scope rejected because Consolidated disclosure exists on Page Z."
- Only if ZERO Consolidated candidates exist anywhere in the pool may you accept a Standalone candidate. If so, set `is_standalone_fallback_active` to true.

STEP 3: SOURCE TYPE HIERARCHY & DEFINITION CLARITY
Among the remaining valid candidates (e.g., all surviving Consolidated candidates):
- Evaluate which candidate most clearly represents the overall company metric value per the accounting definition.
- Apply the source type hierarchy: prefer primary **AUDITED_TABLE** (Statement of Profit and Loss, Balance Sheet, Cash Flow) or formal **FOOTNOTE** definitions over secondary presentations like **KPI_HIGHLIGHTS_BOX**, **GRAPH**, **BAR_CHART**, or **NARRATIVE_PARAGRAPH**, unless the secondary presentation explicitly provides a management-adjusted figure required by the metric definition that is not present in the audited tables.
- Record why secondary candidates were discarded in `rejection_audit_log`: e.g., "[REJECTED Candidate on Page W]: Secondary KPI graph/chart rejected in favor of primary Audited P&L Table on Page V."

OUTPUT DECISION:
Select the single winning candidate and set `final_value` to its `current_year_value` (and populate `winning_candidate`).
If all candidates are rejected in Steps 1-3, set `final_value: null`, `winning_candidate: null`, and explain all rejections in `rejection_audit_log`.

Return JSON matching the `FinalizedMetricPOC3` schema:
```json
{{
  "metric_target": "{metric['name']}",
  "final_value": "string or null",
  "winning_candidate": {{ ...candidate object or null... }},
  "is_standalone_fallback_active": false,
  "rejection_audit_log": [
    "[ACCEPTED Winner on Page X]: Primary Audited Table in Consolidated scope matching exact definition.",
    "[REJECTED Candidate on Page Y]: Standalone scope rejected due to Consolidated preference."
  ],
  "final_forensic_summary": "One summary paragraph explaining the selection."
}}
```
CRITICAL OUTPUT RULE: Return ONLY valid JSON parseable by `json.loads()`.
"""
