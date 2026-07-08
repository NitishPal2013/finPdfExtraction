---
name: visual-verification-audit
description: Performs Phase 3 visual verification audits on extracted financial metrics from Annual Report PDFs using multimodal PDF loading (view_file). Enforces deep forensic checks including longitudinal cross-year consistency, entity scope (Consolidated vs. Standalone), segment/subsidiary footnote boundaries, accounting identity verification, and null spot-checking to prevent superficial number matching. Use this skill whenever verifying extracted financial data against source PDFs or running visual audits.
---

# Phase 3 Visual Verification Audit & Forensic Methodology

## Overview & Core Philosophy
This skill defines the mandatory standard operating procedure (SOP) and deep forensic verification methodology for auditing financial metrics extracted from Annual Report PDFs.
* **Core Philosophy:** *Verification is NEVER just checking if a printed number matches an extracted JSON value.* Superficial number matching fails to catch severe architectural hallucinations (such as segment-level grabs, standalone bias, cash flow conflation, or foreign metric hallucinations).
* True visual verification requires auditing the **longitudinal cross-year consistency**, the **physical page headers**, the **entity scope**, the **note boundaries**, and the **underlying accounting logic**.

---

## 1. Multimodal Verification Workflow & Mandatory Tool Enforcement (`view_file`)

When executing a visual audit or verifying extraction accuracy (false positives, false negatives, True matches) on a source PDF, you MUST transition from text-based scraping to **multimodal visual inspection** by loading the physical rendering of the report via the `view_file` tool.

### 🚨 MANDATORY HARD RULE: ZERO-TOLERANCE FOR TEXT-ONLY AUDITS (YOU MUST CALL `view_file`)
* **ABSOLUTE RULE:** You are **STRICTLY FORBIDDEN** from conducting a "verification audit" or claiming to verify results by solely reading JSON (`.json`), Excel (`.xlsx`), or terminal text logs!
* **MANDATORY TOOL CALL:** For every fiscal year under visual audit, you **MUST explicitly invoke the `view_file` tool** on the source PDF (`<year>.pdf`) so that the physical document (layout, typography, tables, headers, note titles, and numbers) is loaded into your multimodal vision context window.
* **VIOLATION CONSEQUENCE:** Any verification report or response produced without explicitly executing `view_file` on the source PDF is considered **NULL, VOID, and a Severe Behavioral Violation**.

### 🚨 Critical Token & Context Optimization Rule (Single-Pass Loading)
Annual Report PDFs contain hundreds of pages of high-resolution scans and complex tables.
* **SINGLE-PASS BUDGET:** When auditing a fiscal year, you must call `view_file` on the source PDF (`<year>.pdf`) **EXACTLY ONCE**.
* **Why:** Calling `view_file` multiple times on a 250+ page PDF will rapidly saturate your context window and trigger a >1,000,000 token limit error.
* **Audit Workflow:**
  1. **Harvest JSON Audit Trail:** First, inspect the extracted JSON file (`_POC3.json`) via `run_command` or `view_file` to list all found and null metrics, noting their `page_number`, `verbatim_source_text`, `value_num`, and `entity_context`.
  2. **Mandatory Single-Pass PDF Loading (`view_file`):** Call `view_file` on `<year>.pdf` exactly once.
  3. **Visual Cross-Referencing & Physical Evidence:** With the visual pages loaded in your multimodal context window, navigate directly to the physical page numbers and visually verify the headers, table boundaries, and numerical scale (`Lacs` vs `Crores`) across all metrics in a single comprehensive review.

---

## 2. The 5 Deep Forensic Verification Patterns

When verifying any extracted metric against the visual PDF page, you MUST explicitly check and enforce these five forensic patterns:

### Pattern 1: Longitudinal Cross-Year Consistency (The "Why Did It Change?" Rule)
* **The Trap:** A metric might look correct in isolation in FY13, but comparing it against FY14 and FY15 exposes a fatal inconsistency (e.g., identical verbatim phrasing accepted in FY13/FY14 but rejected as `null` in FY15 due to keyword literalism).
* **Mandatory Action:**
  * Always cross-reference the current year's extraction against prior years if available.
  * If a verbatim phrase (e.g., *"Profit before Finance Costs, Depreciation and Exceptional Items"*) was extracted in prior years but suddenly drops to `null` or shifts to a completely different table type, **flag it immediately as a Longitudinal Anomaly / Literalism Bug**.

### Pattern 2: Visual Header & Entity Scope Audit (Consolidated vs. Standalone)
* **The Trap:** Management frequently presents clean summary tables in the Standalone Directors' Report or Management Discussion & Analysis (MD&A). Naive verification passes a number match even when statutory Consolidated statements sit ignored later in the report.
* **Mandatory Action:**
  * Look beyond the number table to read the **running page header** at the very top of the physical page and the **chapter/section title**.
  * If the header reads *"Standalone Financial Statements"*, *"Directors' Report"*, or *"MD&A"*, check the Table of Contents to verify if **Consolidated Financial Statements** exist in that filing.
  * If Consolidated statements exist, but the extraction grabbed a Standalone table, **FAIL the verification** and flag it as a **Scope Preference Violation / Ranking Error**.

### Pattern 3: Footnote & Section Boundaries (The Segment & Subsidiary Trap)
* **The Trap:** An extracted number might match a footnote table exactly (e.g., Page 165 or Page 148), but reading the footnote heading reveals it is **Note on Segment Reporting** (Note 38/54) or a **Subsidiary Concession Project Disclosure** (Note 39).
* **Mandatory Action:**
  * Always audit the **Note Number, Note Title, and introductory footnote text** at the boundary of the table.
  * If the table is inside **Segment Reporting / Segment Information**, **REJECT IT IMMEDIATELY** for whole-company metrics (EBIT, Revenue, EBITDA, Margin). Segment profit is a partial division result!
  * If the table is inside a **Subsidiary / Joint Venture / Project Note**, **REJECT IT IMMEDIATELY** for group-level metrics (Collections, Debt, Cash Flow).

### Pattern 4: Accounting Logic & Verbatim Label Verification
* **The Trap:** An AI might grab `(9,338.38)` from the Cash Flow Statement and call it "Cash Loss", or grab *"amount available for appropriation"* and call it "Distributable Cash Flow".
* **Mandatory Action:**
  * Verify what the line item actually represents by testing it against accounting laws:
  * **Cash Loss / Cash Earnings:** Must come from an Income Statement/MD&A accrual table ($\text{PAT} + \text{D\&A}$). If it comes from the *Statement of Cash Flows* (Operating Cash Flow / CFO), **REJECT IT**.
  * **Distributable Cash Flow:** Check if the company is under Ind AS / Indian GAAP. Manufacturing companies under Ind AS do not report DCF (an American MLP/REIT metric). If the label says *"available for appropriation"* or *"retained earnings"*, **REJECT IT as a Foreign Metric Hallucination**.
  * **EBIT Margin vs. EBITDA Margin:** Check the math. Statutory EBIT Margin must always be numerically lower than EBITDA Margin. If *"Operating Profit Margin"* was grabbed for EBIT Margin without verifying depreciation exclusion, **REJECT IT**.

### Pattern 5: The "Null" Spot-Check Protocol (True vs. False Negatives)
* **The Trap:** Assuming that if the JSON reports `null` (0 candidates found), the metric genuinely does not exist in the report.
* **Mandatory Action:**
  * For every audit, you must spot-check at least 3–5 key `null` metrics:
  * **P&L & Exceptional Items Check:** Did the company report Exceptional/Extraordinary items? If yes, check if an Adjusted EBITDA or Adjusted EBIT figure/label was printed but ignored due to keyword literalism.
  * **CARO Auditor's Report Check:** Did the statutory auditor certify Clause (x) regarding Cash Losses under CARO? If yes, and `Cash Loss Incurrence Status` returned `null`, flag it as a **False Negative**.
  * Only confirm a `null` as a **True Negative** if the metric is genuinely foreign to the sector (e.g., ARPU, Constant Currency Revenue, Bookings in a steel/manufacturing company).

### Pattern 6: Cross-Metric Conflict & Similarity Audit (The "Why Are These Identical?" Rule)
* **The Trap:** When two distinct metrics with similar names or related concepts (such as `EBITDA` vs. `Adjusted EBIT`, `EBIT` vs. `Adjusted EBIT`, `EBITDA` vs. `Adjusted EBITDA`, `CFO` vs. `Free Cash Flow`, or `Cash Earnings` vs. `EBITDA`) return the **exact same numerical value** or present conflicting accounting logic.
* **Mandatory Action:**
  * Always cross-check all extracted values in a fiscal year against each other.
  * Whenever two distinct metrics return the **exact same value** (or when a metric like Adjusted EBIT equals EBITDA), you must immediately perform a **Cross-Metric Conflict & Accounting Logic Audit**:
    1. **Check the Verbatim Line Item:** Did the model map the exact same line item string (e.g., *"Profit before Interest, Depreciation & Exceptional Items"*) to both buckets?
    2. **Check the Accounting Definition:** If the line item says *"before Depreciation"* (meaning D&A has NOT been subtracted), it is **EBITDA / Adjusted EBITDA**, NOT **Adjusted EBIT**! In Adjusted EBIT, Depreciation MUST be subtracted!
    3. **Validate True vs. False Match:** Determine if the identical values are accounting-wise justified (e.g., when zero exceptional items exist, `EBITDA` equals `Adjusted EBITDA`, or `EBIT` equals `Adjusted EBIT`) OR if it is a **Cross-Metric Misclassification Bug** (where the AI got confused by similar naming words like "EBIT" vs "EBITDA" or "Adjusted").
    4. **Resolution:** If a metric like Adjusted EBIT was wrongly assigned an EBITDA line item because the model conflated the labels, **FAIL the verification** and report it as a **Cross-Metric Conflation / Label Similarity Error**.

---

## 3. Master Verification Checklist

When executing this skill, complete this 9-point audit checklist before signing off on any extracted dataset:

```markdown
- [ ] 1. **Single-Pass Loading:** Was `view_file` called exactly once on the source PDF to preserve token budget?
- [ ] 2. **Longitudinal Check:** Was the metric compared against prior years to detect unexplained drops to `null` or shifts in table sources?
- [ ] 3. **Entity Header Audit:** Does the running header on the physical page confirm **Consolidated** scope (or valid Standalone fallback)?
- [ ] 4. **Segment Note Firewall:** Is the figure located outside Note on Segment Information (e.g., Note 38/54)?
- [ ] 5. **Subsidiary Note Firewall:** Is the figure located outside subsidiary/project footnotes (e.g., Note 39)?
- [ ] 6. **Statement Type Proof:** Is Cash Loss/Earnings from an Income Statement/MD&A accrual table rather than CFO?
- [ ] 7. **Accounting Identity Verification:** Does the metric satisfy basic accounting laws (e.g., $EBIT < EBITDA$; no REIT metrics in Ind AS)?
- [ ] 8. **Null Spot-Check (False Negatives):** Were key `null` metrics visually checked against the P&L and CARO Report to rule out literalism bugs?
- [ ] 9. **Cross-Metric Conflict Audit:** Were identical values between similar-named metrics (e.g. EBITDA vs. Adjusted EBIT) audited to verify accounting validity vs. label conflation?
```

---

## 4. Deliverable Format

When reporting back the results of a visual verification audit executed via this skill, output a structured markdown audit table in the following format:

| FY Year | Metric Name | Extracted Value | Page # | Visual Verification Status | Context (Consol/Standalone) | Forensic Findings & Discrepancies |
| :--- | :--- | :---: | :---: | :---: | :---: | :--- |
| FY... | ... | ... | ... | **VERIFIED** / **FALSE POSITIVE** / **FALSE NEGATIVE** / **SCOPE ERROR** | ... | Detailed explanation referencing the 5 forensic patterns... |
