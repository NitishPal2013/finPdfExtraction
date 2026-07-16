# Phase 3 Visual Verification Audit: Dual-Scope Extraction Checklist & SOP

## 📌 Executive Summary & Purpose
Following our first-principles architectural upgrade (`POC3` with **Scope Conviction Proofs**), dual-scope extractions (`Consolidated` & `Standalone`) have been successfully run across four target fiscal years of **Jindal Saw Ltd**: **FY13, FY16, FY18, and FY21**.

This document serves as the **Master Verification TODO & SOP Guide** for conducting exhaustive Phase 3 Visual Verification Audits on the generated outputs against the original source Annual Report PDFs.

---

## 📂 Target Audit Roster & File Registry

All dual-scope workbooks (`_POC3.xlsx`) now contain **4 sheets**:
1. `Consolidated Disclosures` (containing `Scope Conviction Proof` in Column D)
2. `Standalone Disclosures` (containing `Scope Conviction Proof` in Column D)
3. `Candidate Audit Log` (containing all harvested candidates across all 37 queries)
4. `Coverage & Stats` (Dual-Scope comparison table)

### Target Filings to Verify:
* [ ] **FY13 (2012-13)**
  * Source PDF: `file:///Users/fti/personal_work/nair/pdfs/Jindal Saw Ltd/13.pdf`
  * Excel Workbook: `file:///Users/fti/personal_work/nair/pdfs/Jindal Saw Ltd/13_POC3.xlsx`
  * JSON Audit Trail: `file:///Users/fti/personal_work/nair/pdfs/Jindal Saw Ltd/13_POC3.json`
* [ ] **FY16 (2015-16)**
  * Source PDF: `file:///Users/fti/personal_work/nair/pdfs/Jindal Saw Ltd/16.pdf`
  * Excel Workbook: `file:///Users/fti/personal_work/nair/pdfs/Jindal Saw Ltd/16_POC3.xlsx`
  * JSON Audit Trail: `file:///Users/fti/personal_work/nair/pdfs/Jindal Saw Ltd/16_POC3.json`
* [ ] **FY18 (2017-18)**
  * Source PDF: `file:///Users/fti/personal_work/nair/pdfs/Jindal Saw Ltd/18.pdf`
  * Excel Workbook: `file:///Users/fti/personal_work/nair/pdfs/Jindal Saw Ltd/18_POC3.xlsx`
  * JSON Audit Trail: `file:///Users/fti/personal_work/nair/pdfs/Jindal Saw Ltd/18_POC3.json`
* [ ] **FY21 (2020-21)**
  * Source PDF: `file:///Users/fti/personal_work/nair/pdfs/Jindal Saw Ltd/21.pdf`
  * Excel Workbook: `file:///Users/fti/personal_work/nair/pdfs/Jindal Saw Ltd/21_POC3.xlsx`
  * JSON Audit Trail: `file:///Users/fti/personal_work/nair/pdfs/Jindal Saw Ltd/21_POC3.json`

---

## 🚨 Critical Token & Context Management Rule (Mandatory SOP: Subagent Delegation)
Annual Report PDFs contain hundreds of high-resolution visual pages. When an agent invokes `view_file` on a binary `.pdf` file, the multimodal visual rendering is loaded into the context window.
* **CRITICAL RULE (NO DIRECT LOADING IN PARENT CONTEXT)**: Do **NOT** invoke `view_file` on binary `.pdf` files right inside the main parent context window! Doing so saturates and pollutes the parent agent's context.
* **MANDATORY SUBAGENT DELEGATION**: Always spawn a dedicated verification subagent (via `invoke_subagent` using `self` or `research` type) tasked specifically with loading `[year].pdf` via `view_file`. The subagent will physically inspect the visual pages inside its isolated context window and report back the clean verification findings.
* **SINGLE-PASS BUDGET IN SUBAGENT**: Inside the subagent, call `view_file` on `[year].pdf` **EXACTLY ONCE** (`Step 2`) to perform the comprehensive visual check across all target pages simultaneously.

---

## 📋 Strict 4-Step Verification Protocol

For each fiscal year above, execute the following forensic verification sequence:

### Step 1: Harvest Extraction Targets from Workbook/JSON
Run a quick python or grep check on `[year]_POC3.json` or `[year]_POC3.xlsx` (`Consolidated Disclosures` & `Standalone Disclosures`).
Make a complete check-list of all metrics where `final_value` is NOT `REJECTED ALL` and NOT `0 CANDIDATES`. Record:
* `metric_target`
* `final_value`
* `entity_context` (`Consolidated` vs. `Standalone`)
* `scope_conviction_proof` (`Visual surrounding clues cited by model`)
* `source_type` (`AUDITED_TABLE`, `FOOTNOTE`, `NARRATIVE/CHARTS`)
* `page_number` (`Physical 1-indexed PDF page`)

### Step 2: Single-Pass Direct Visual Inspection (`view_file`)
Call `view_file` on `file:///Users/fti/personal_work/nair/pdfs/Jindal Saw Ltd/[year].pdf` **EXACTLY ONCE**.
With the visual rendering loaded in context, navigate to the physical page numbers (`page_number`) for every `FOUND` metric identified in Step 1.

### Step 3: Execute the 3-Point Forensic Verification Checklist
For every `FOUND` metric on its physical PDF page, rigorously audit:
1. **Character-for-Character Numerical Accuracy**: Confirm that the number printed on the sheet exactly matches `final_value`. Verify decimal precision (`.00`), negative signs / brackets, and scale (`Rs in Lakhs` vs. `Rs in Crores` vs. `Millions`).
2. **Scope Conviction & Running Header Audit (`Consolidated vs. Standalone`)**:
   * Inspect the physical running header at the top of the visual page (e.g., *"CONSOLIDATED FINANCIAL STATEMENTS"* vs. *"STANDALONE FINANCIAL STATEMENTS"* vs. *"BOARD'S REPORT"*).
   * Verify whether the model's `scope_conviction_proof` accurately reflects what is printed on the sheet.
   * *Critical Rule*: If a metric was extracted as `Consolidated`, but the running header on that page reads `Standalone Financial Statements`, flag it immediately as a **Scope Error ❌**!
3. **Source Attribution & Table Type**: Confirm if the number genuinely originated from a primary statutory table (`AUDITED_TABLE` - Balance Sheet, P&L, Cash Flow), a statutory footnote (`FOOTNOTE`), or management commentary (`NARRATIVE/CHARTS`).

### Step 4: Spot-Check Nulls & Rejections
For 2 to 3 key metrics that returned `REJECTED ALL` or `0 CANDIDATES` (e.g., `Distributable Cash Flow`, `GAAP One-time Adjustment`), visually inspect the P&L / Auditor's Report / Exceptional Items Note on the rendered PDF view to confirm that the item was truly absent or `NOT_INCURRED`.

---

## 📊 Deliverable Format: Verification Audit Report Table

Upon completing the verification of a fiscal year, document your findings using the standardized table below:

```markdown
### Verification Audit Report: [FY Year]

| Scope | Metric Name | Extracted Value | Physical Page # | Scope Conviction Proof Audit | Source Type | Visual Verification Status | Forensic Notes / Discrepancies |
| :--- | :--- | :---: | :---: | :--- | :---: | :---: | :--- |
| Consolidated | Adjusted EBITDA | `22,994.02` | P. 156 | Header confirmed: 'Consolidated Statement of Profit and Loss' | `AUDITED_TABLE` | **VERIFIED ✅** | Exact match with P&L statutory row. |
| Standalone | EBITDA | `1,25,967.22` | P. 22 | Header confirmed: 'Board's Report' (Standalone results) | `AUDITED_TABLE` | **VERIFIED ✅** | Exact match with Board's Report text & P&L math. |
```

---

## 📌 Status Checklist

- [ ] Complete Phase 3 Visual Verification Audit for **FY13** (`13.pdf`)
- [ ] Complete Phase 3 Visual Verification Audit for **FY16** (`16.pdf`)
- [ ] Complete Phase 3 Visual Verification Audit for **FY18** (`18.pdf`) *(Already verified via forensic visual audit)*
- [ ] Complete Phase 3 Visual Verification Audit for **FY21** (`21.pdf`)
