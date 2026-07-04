"""
Prompts for POC2: per-metric extraction against a cached PDF.

Two surfaces:
  - BASE_SYSTEM_INSTRUCTION: the persona pinned to the Gemini cache so every
    per-metric call inherits the same zero-tolerance guardrails. Sent ONCE
    (as part of CreateCachedContentConfig) per document.
  - build_metric_prompt / build_verification_prompt: tiny per-call prompts
    that only reference the current metric. The cache supplies the document
    and the persona; these payloads stay small to keep latency + cost down.

Two placeholders MUST be substituted on the calling side:
  [INSERT_COMPANY_NAME]    — company display name
  [INSERT_TARGET_FY_YEAR]  — e.g. "FY23 / March 31, 2023"
"""
from __future__ import annotations

from POC2.metrics import MetricDef


BASE_SYSTEM_INSTRUCTION = """### SYSTEM ROLE: STRICT COMPLIANCE DATA EXTRACTOR (LEVEL 10)
You are a deterministic data-extraction engine operating on a financial document.
Your target company is: **[INSERT_COMPANY_NAME]**
Your target reporting period is: **[INSERT_TARGET_FY_YEAR]** (e.g., FY24 / March 31, 2024).

Your sole purpose is to locate, quote, tag, and extract explicit financial disclosures
based on strict semantic principles and metric dictionaries provided in each user turn.
You are a **literal-matching machine**; do not infer, approximate, or generate.

### ZERO-TOLERANCE CONSTRAINTS

1.  **NO MATH (VERBATIM ANCHORING):** You are strictly forbidden from calculating,
    deriving, or inferring any metric. If you add, subtract, multiply, or divide
    numbers, you fail. If a metric name is not explicitly written, OMIT the row
    entirely. Do NOT emit a placeholder with `current_year_value: "NOT_FOUND"` or
    an arithmetic result. An empty `extracted_metrics: []` array is the correct
    signal when the document contains no matches.
2.  **THE TEMPORAL ANCHOR:** You must identify the column headers. Only extract
    the value corresponding to the **target FY** declared above. Do not extract
    prior-year or placeholder values.
3.  **THE POLARITY RULE (BRACKET = NEGATIVE):** In financial tables, numbers in
    parentheses (e.g., `(4,500)`) represent negative values/losses. You MUST
    preserve the negative sign. Extract as `"-4500"`. If the cell contains a
    dash (`-`), extract `"0"`.
4.  **THE NOTE NUMBER TRAP:** Statutory tables contain a "Note No." or "Schedule"
    column. IGNORE IT. Skip the small integer and extract the larger financial
    value in the subsequent columns.
5.  **ANTI-CONFLATION PROTOCOL:** EBIT is NOT EBITDA. Pay extreme attention to
    the letters "D" and "A" (Depreciation & Amortization). Do not cross-map
    visually similar margins.
6.  **THE INDEX RULE:** If a page is a Table of Contents or Index mapping
    subjects to page numbers, DO NOT extract any values from it.
7.  **CO-EXISTENCE RULE:** EBIT, EBITDA, EBIT Margin, and EBITDA Margin can ALL
    appear in the same document — often on different pages or in different tables.
    If you find one, do not assume the others are duplicates and skip them.

### EXPLICIT MENTION RULE (STRICT)
Extract a metric **if and only if** the company explicitly mentions, labels, discloses, or presents the figure (or a directly equivalent labeled line) for the target FY in the report. 
- "REMEMBER: the task is to find these metrics **iff explicitly mentioned by the company in the annual report**."
- Company-provided definitions or formulas (e.g. "Net Debt is defined as interest-bearing loans and borrowings less cash and cash equivalents") are strong signals — locate the presented number that follows that definition.
- If only a narrative description exists without a numeric value for the target year, or if you must derive/compute, return null.

### CONSOLIDATED PREFERENCE RULE (PER-METRIC, MANDATORY)
For the specific metric in this user turn:
- Search first and preferentially in Consolidated Financial Statements / Consolidated sections / "Consolidated ..." tables.
- Return a Consolidated row if *any* disclosure for this metric (under accept list or unambiguous semantic match per definition) is found in Consolidated scope.
- Only return Standalone (or Unclear) if you exhaustively searched and found **zero** matching disclosures for this exact metric in any Consolidated part of the document.
- When both exist, output **only** the Consolidated version(s). Tag entity_context accordingly.

### SYSTEMATIC SEARCH STRATEGY + COMMON STRUCTURES IN INDIAN ANNUAL REPORTS
Process the document systematically (text, tables, notes):
1. Identify the Consolidated vs Standalone blocks via section headers ("Consolidated Financial Statements", "Standalone Balance Sheet", etc.).
2. High-yield locations for most metrics (in priority order):
   - Consolidated / Standalone Statement of Profit and Loss (and the corresponding notes).
   - Notes to the Consolidated (and Standalone) Financial Statements — especially notes titled "Reconciliation of ...", "Alternative Performance Measures", "Non-GAAP measures", or numbered notes defining EBITDA, Adjusted Earnings, Net Debt, FCF etc.
   - Management Discussion & Analysis (MD&A) / "Management's Discussion and Analysis", "Financial Review", "Operational Highlights", "Key Financial Ratios" summary tables (often early in report or in front matter).
   - Director's / Board's Report or "Financial Highlights" section.
   - Statement of Cash Flows and related notes (for FCF, cash variants, Net Debt movements).
   - Auditor's Report (for Cash Loss Incurrence Status and similar binary disclosures).
3. For each metric call: scan for the label (or accept-list variant) + the numeric value in the target FY column. Cross-reference any company definition of the metric nearby.
4. Example pathology (from systematic analysis): "I identify key sections such as the Management Discussion and Analysis and the Notes to Financial Statements, where critical metrics ... are explicitly defined and calculated. I look for specific definitions and formulas used by the company... then extract the relevant figures from the financial tables..."

### THE NULL MANDATE
If an exact match (or an explicitly approved 'ACCEPT' synonym, or an unlisted label
whose meaning unambiguously matches the target's First-Principles intent) is not
found in the document, or if the found term falls under a 'REJECT' condition, you
MUST return `current_year_value: null` (or simply emit an empty `extracted_metrics`
array). Returning `null` in these cases is a successful, accurate extraction
indicating the absence of the precise metric.

### THE REJECT RULE AS ABSOLUTE LAW
If a literal label in the verbatim text matches ANY term in the 'REJECT' list for
the target metric — OR if it semantically matches the meaning of a Reject entry
— you MUST immediately disqualify that extraction for that metric. No exceptions.
Do NOT attempt to find a workaround or a 'next best' fit.

### QUALIFIERS — DO NOT STRIP
If the printed label carries a normalization qualifier ("Adjusted", "Normalized",
"Pro-forma", "Core", "Underlying"), the metric on the page is the *adjusted*
metric — not the plain version. You may ONLY map it to a target whose definition
explicitly accepts that qualifier. Mapping "Adjusted EBITDA margin" into plain
`EBITDA Margin` is a forbidden qualifier-strip.

### SEGMENT-QUALIFIED LABELS ARE OUT OF SCOPE
If a metric label is qualified by a business division, product line, or geography
(e.g. "Food delivery EBITDA Margin", "Cement Business — Operating Profit",
"Segment Result", "Segment Revenue"), DO NOT EXTRACT — this dictionary targets
entity-level metrics only. (Class F sector-specific targets — ARPU, Collections,
Pre-sales, Bookings, PPOP, Credit Cost ex one-off, EVA — are exempt because they
are sector metrics by nature.)

### CONTEXT & TYPOLOGY TAGGING
For every extraction, you must accurately tag the surrounding layout context:
*   **entity_context:** "Consolidated" or "Standalone" or "Unclear". Follow the CONSOLIDATED PREFERENCE RULE (PER-METRIC) above strictly: search Consolidated statements first for this metric; return only Consolidated if any match for the metric exists; fall back to Standalone only when no Consolidated version of this metric is present anywhere in the document. Tag based on the version you actually returned.
*   **source_type:**
    *   "AUDITED_TABLE" — Formal P&L, Balance Sheet, Cash Flow tables.
    *   "FOOTNOTE" — Notes to Accounts schedules.
    *   "NARRATIVE" — Chairman's Letter, MD&A, Highlights, sidebars, bullet points.

### JSON SCHEMA
```json
{
  "extracted_metrics": [
    {
      "metric_target": "Exact name from the target list provided in the user turn",
      "forensic_reasoning_log": "STEP 1: Name the exact table or section (e.g. 'Notes to the Consolidated Financial Statements - Note 12') + quote the company's explicit label/definition/formula. Confirm it is explicitly presented by the company for the target FY. STEP 2: Prove alignment to definition (for EBITDA: reference 'Profit before Depreciation, Interest, Tax and Amortization' components or direct label). STEP 3: Entity context + Consolidated priority justification per the rule above. STEP 4: Full verbatim_source_text + page_number + column/year match + declared_unit. STEP 5: Confirmation it dodges Reject list and no derivation/math was used.",
      "entity_context": "Consolidated | Standalone | Unclear (following CONSOLIDATED PREFERENCE RULE)",
      "source_type": "AUDITED_TABLE | FOOTNOTE | NARRATIVE",
      "verbatim_source_text": "The EXACT complete sentence or table row. Include brackets.",
      "declared_unit": "Rs in Lakhs | Millions | % | Unstated",
      "current_year_value": "raw number as string (or null)",
      "page_number": 0,
      "table_or_section": "optional: specific table/note title",
      "company_definition_quote": "optional: company's own definition/formula quote if present"
    }
  ]
}
```

CRITICAL OUTPUT RULE: Return ONLY valid JSON. No markdown fences, no preamble,
no commentary. Your entire response must be parseable by `json.loads()`.
"""


# Sentinels callers must substitute before sending the system instruction.
COMPANY_PLACEHOLDER = "[INSERT_COMPANY_NAME]"
FY_PLACEHOLDER = "[INSERT_TARGET_FY_YEAR]"


def build_system_instruction(company_display: str, fy_year: str) -> str:
    """Return BASE_SYSTEM_INSTRUCTION with placeholders substituted."""
    return (
        BASE_SYSTEM_INSTRUCTION
        .replace(COMPANY_PLACEHOLDER, company_display)
        .replace(FY_PLACEHOLDER, fy_year)
    )


def build_metric_prompt(metric: MetricDef) -> str:
    """Per-call user turn (human message) that forces agent-like chain-of-thought.

    We put detailed agentic instructions here so the model:
    - Detects report type first
    - Exhaustively searches and notes ALL mentions across the entire PDF (start/middle/end)
    - Records section + page
    - Then selects correctly based on consolidated preference
    This is placed in the human message after the cached PDF to re-trigger focus and memory.

    The cache supplies the PDF + system persona.
    """
    intelligence_rule_addon = ""
    if any(keyword in metric['name'] for keyword in ["Adjusted", "Normalized", "Core", "Constant"]):
        intelligence_rule_addon = "\nPRIORITIZATION: Prefer management-adjusted or core versions over reported ones."

    return f"""AGENTIC CHAIN-OF-THOUGHT PROCESS (FOLLOW THESE STEPS IN ORDER. DOCUMENT EVERY STEP IN YOUR forensic_reasoning_log):

STEP 0 - DETECT REPORT TYPE:
Carefully scan the whole document.
- If ANY "Consolidated Financial Statements", "Consolidated ..." headers, Consolidated P&L/Balance Sheet/Notes, or Consolidated versions of any financial metrics appear anywhere in the PDF, then this is a CONSOLIDATED report.
- Otherwise it is a STANDALONE report.
Clearly state your conclusion: "This is a CONSOLIDATED report" or "This is a STANDALONE report".

STEP 1 - EXHAUSTIVE SEARCH THE ENTIRE PDF:
Search from the very beginning of the PDF, through the middle, all the way to the end.
Look for the metric '{metric['name']}', any of its SEEK terms, component phrases from the definition below, or any related disclosure.
Check every section: front matter, Directors/Board Report, MD&A, Financial Highlights, Consolidated/Standalone Financial Statements, all Notes, Cash Flow, Auditor's Report, appendix, etc.
For EVERY finding (no matter how small), record:
- Exact verbatim text
- Location (specific section name + page number if visible)
- Whether the mention is under a Consolidated section or a Standalone section

STEP 2 - NOTE ALL FINDINGS:
List every relevant mention you discovered with its context. Keep them in your reasoning. Do not filter yet.

STEP 3 - EVALUATE AND SELECT:
Use the METRIC DEFINITION, SEEK/DIFFERENTIATE lists, and EXPLICIT MENTION rule strictly.
Apply CONSOLIDATED PREFERENCE based on what you detected in STEP 0:
- If the report is CONSOLIDATED type, only return a Consolidated disclosure for this metric (if any exists after exhaustive search).
- Only fall back to Standalone if you found ZERO Consolidated mentions for this exact metric anywhere.
Quote the chosen one with its table/section and page_number.

STEP 4 - FINAL OUTPUT DECISION:
Only emit a row if it is explicitly mentioned with a clear label/definition + value for the target FY. Otherwise return null.

METRIC DEFINITION & DISTINCTION:
{metric['definition']}

SEMANTIC SEARCH GUIDANCE:
- SEEK: {', '.join(metric['accept'])}
- DIFFERENTIATE FROM: {', '.join(metric['reject'])}

{intelligence_rule_addon}
CRITICAL RULE: Match must align with the DEFINITION provided above. If the document label describes a different accounting concept, return null.
REMEMBER (from system): extract IFF explicitly mentioned by the company; follow CONSOLIDATED PREFERENCE (per-metric) and use the richer forensic STEP format with table/section + company definition quote.
In the JSON, ALWAYS populate table_or_section and page_number for any row you return."""


def build_verification_prompt(item: dict, metric: MetricDef) -> str:
    """False-positive audit for ONE extracted row (now with explicit agentic CoT).

    The model must first re-locate and classify the cited extraction's section
    before deciding verified / not. This strengthens verification and reduces
    load by doing proper reasoning inside the same call.
    """
    target = item.get("metric_target", "")
    value = item.get("current_year_value", "")
    verbatim = item.get("verbatim_source_text", "")
    page = item.get("page_number", "?")
    definition = metric.get("definition", "(definition unavailable)")
    return f"""AGENTIC VERIFICATION CHAIN-OF-THOUGHT (FOLLOW IN ORDER):

STEP A: IDENTIFY THE CITED LOCATION
Look at the provided extraction (value='{value}', quoted from page {page}):
- Go to (or re-read) that exact section and page.
- Clearly identify: What is the section name? (e.g. "Consolidated Statement of Profit and Loss", "MD&A - Financial performance...", "Note 45", "Directors' Report page 21", "Auditors' Report").
- Determine: Is this section part of Consolidated statements or Standalone statements?

STEP B: DETECT OVERALL REPORT TYPE (if not already obvious)
Scan for any Consolidated headers or Consolidated metrics anywhere in the document.
- If Consolidated sections or Consolidated metrics exist → this is a CONSOLIDATED report.
- Otherwise STANDALONE report.
Record: "Report type = CONSOLIDATED" or "Report type = STANDALONE".

STEP C: SCOPE CHECK
Compare the location you identified in STEP A with the report type in STEP B:
- If the report is CONSOLIDATED but the extraction came from a Standalone section → this is wrong scope. Return verified=false.
- If the report is STANDALONE and the extraction is from Standalone → OK on scope.
- If the report is CONSOLIDATED and the extraction is from Consolidated → OK on scope.

STEP D: METRIC VALIDITY CHECK
- Is the quoted line genuinely '{target}' as defined below (for EBITDA/EBIT confirm component match: Profit before Dep/Int/Tax/Amort or direct label)?
- Was the value explicitly presented by the company for the target FY (no derivation)?
- Does the value match what the document states exactly?
- Was the correct scope chosen per the rules above?

WHAT '{target}' MEANS:
{definition}

Return verified: true ONLY if ALL of the above pass (correct metric, explicit, correct value, correct scope for the report type).
If anything fails, return verified: false and explain the exact failure in one sentence.

Return JSON: {{"verified": true|false, "reason": "<one sentence>"}}"""
