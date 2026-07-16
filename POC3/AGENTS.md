# POC3 Architecture: Dual-Scope Two-Stage Extraction & Multi-Sheet Workbook Engine

`POC3` is an exhaustive, high-precision financial data extraction engine designed to isolate and verify financial disclosures across complex multi-hundred-page annual report PDFs. Unlike traditional extraction pipelines that prematurely discard or average candidate figures, `POC3` decouples **Broad Candidate Discovery (`Layer 1`)** from **Scope-Targeted Forensic Finalization (`Layer 2`)**, outputting four clean, highly structured Excel worksheets (`_POC3.xlsx`) for every target company and fiscal year.

---

## 🏗️ Architectural Workflow & Core File References

```
[Annual Report PDF] -> Layer 1: Candidate Harvesting -> [Candidates Pool (Consolidated & Standalone)]
                                                                   |
                                          +------------------------+------------------------+
                                          | (Partitioned by Scope)                          |
                                          v                                                 v
                            Layer 2: Consolidated Pass                        Layer 2: Standalone Pass
                            (Bypassed if 0 Candidates)                        (Bypassed if 0 Candidates)
                                          |                                                 |
                                          +------------------------+------------------------+
                                                                   |
                                                                   v
                                                  [4-Sheet Excel Workbook (_POC3.xlsx)]
                                                  1. Consolidated Disclosures Sheet
                                                  2. Standalone Disclosures Sheet
                                                  3. Candidate Audit Log Sheet
                                                  4. Coverage & Stats Summary Sheet
```

### 1. `Layer 1: Exhaustive Candidate Harvesting Engine` ([POC3/prompt.py](file:///Users/fti/personal_work/nair/POC3/prompt.py#L21-L100))
* **Objective:** Scan the PDF from cover to cover and capture every valid mention or formulaic candidate figure for a target metric (`37 target metrics`).
* **Section Traversal Strategy:** Iterates systematically across TOC, Highlights, Infographics, Directors' Report, MD&A, Consolidated Statements, Standalone Statements, and Notes to Accounts (`prompt.py:L39-44`).
* **Dual-Scope Capture Rule (`Rule #1`):** Captures **BOTH** Consolidated and Standalone figures in the same pass (`prompt.py:L29`). Never discards a Standalone figure just because a Consolidated figure exists.
* **Physical Line Proofs:** Mandates 1-indexed `page_number`, `printed_page_number`, `verbatim_source_text`, `page_verbatim_proof_above`, and `page_verbatim_proof_below` (`models.py:L50-65`).

### 2. `Layer 2: Scope-Targeted Precision Finalization Engine` ([POC3/prompt.py](file:///Users/fti/personal_work/nair/POC3/prompt.py#L101-L169))
* **Objective:** Evaluate harvested candidates against strict accounting firewalls and output a verified winner per entity scope.
* **Dual-Slot Finalization (`extractor.py:L364-427`):**
  * Each metric's harvested candidates (`harvested_candidates`) are partitioned into `cons_cands` (`entity_context in ("Consolidated", "Unclear")`) and `std_cands` (`entity_context in ("Standalone", "Unclear")`).
  * **API Cost Shield (Bridge Filter):** If a slot has `0 candidates` (`len == 0`), Layer 2 API calls are immediately bypassed right at the Python bridge (`extractor.py:L256-264`). If candidates exist (`len > 0`), Layer 2 is invoked with a scope-specific prompt (`target_scope="Consolidated"` or `"Standalone"`).
* **Forensic Checklist (Strict 4-Step Hierarchy):**
  * **Step 1 (`Whole-Company Scope Pruning`):** Strictly bans and rejects partial business disclosures (Segment reporting notes `38/54`, subsidiary-only notes `39`, Joint Ventures, or proxy formulas like CFO as Cash Loss) (`prompt.py:L127-L132`).
  * **Step 2 (`Exclusion & Formula Firewalls`):** Strictly enforces definition formulas from `metrics.py` (e.g., verifying that Depreciation & Amortization, Interest, Taxes, and Exceptional One-Time Items were properly removed) (`prompt.py:L133-L138`).
  * **Step 3 (`Scope Targeting`):** Evaluates strictly within the target pass (`Consolidated` vs. `Standalone`) (`prompt.py:L139-L153`).
  * **Step 4 (`Source Type Hierarchy`):** Ranks `AUDITED_TABLE > FOOTNOTE > NARRATIVE_PARAGRAPH / CHARTS` (`prompt.py:L154-L167`).

---

## 📂 Codebase Module Map (`POC3/`)

| File | Purpose & Architecture Role |
| :--- | :--- |
| **[`POC3/extractor.py`](file:///Users/fti/personal_work/nair/POC3/extractor.py)** | **Main Engine / CLI Entrypoint.** Coordinates Layer 1 file uploads, caching, concurrency (`asyncio.Semaphore`), candidate partitioning, Layer 2 dual-slot invocations, and returns `ExtractionResultPOC3` (`models.py:L101-L118`). |
| **[`POC3/prompt.py`](file:///Users/fti/personal_work/nair/POC3/prompt.py)** | **Prompt Construction Layer.** Defines `BASE_SYSTEM_INSTRUCTION` (`Layer 1`), `build_candidate_extraction_prompt`, and `build_finalization_prompt` with dynamic `target_scope` injection. |
| **[`POC3/models.py`](file:///Users/fti/personal_work/nair/POC3/models.py)** | **Pydantic Schemas.** Defines `CandidateMetricPOC3` (`Layer 1 candidate schema`), `CandidateListResponse`, and `FinalizedMetricPOC3` (`Layer 2 winner/audit schema`). |
| **[`POC3/metrics.py`](file:///Users/fti/personal_work/nair/POC3/metrics.py)** | **Source of Truth for Target Metrics.** Defines `METRIC_METADATA` (`37 metrics across 6 categories`), including seek terms (`accept`), reject terms (`reject`), definitions, and `layer2_rules` accounting firewalls. |
| **[`POC3/excel_export.py`](file:///Users/fti/personal_work/nair/POC3/excel_export.py)** | **Multi-Sheet Workbook Generator.** Formats and outputs `_POC3.xlsx` containing our 4 distinct worksheets. |
| **[`POC3/run_batch_FY16_FY22.py`](file:///Users/fti/personal_work/nair/POC3/run_batch_FY16_FY22.py)** | **Batch Orchestrator.** Runs multi-year extraction pipelines sequentially across annual report PDFs. |

---

## 📑 4-Sheet Excel Workbook Specification (`_POC3.xlsx`)

Every execution of `POC3/extractor.py` generates an Excel workbook formatted into 4 specialized worksheets (`excel_export.py:L55-L185`):

### Sheet 1: `Consolidated Disclosures`
* **Purpose:** Finalized disclosures evaluated strictly for the **Consolidated Group Entity** across all 37 target metrics.
* **Columns:** `Metric Target`, `Final Value`, `Entity Context`, `Source Type`, `Page #`, `Printed Page`, `Table / Section`, `Audit Log Summary`, `Verbatim Source Text`.
* **Granular Null Statuses:**
  * **`0 CANDIDATES`**: Displayed when Layer 1 found `0 candidates` across the entire document for this Consolidated metric.
  * **`REJECTED ALL`**: Displayed when Layer 1 found candidate mentions, but Layer 2 rejected all of them due to accounting firewalls or scope mismatches.

### Sheet 2: `Standalone Disclosures`
* **Purpose:** Finalized disclosures evaluated strictly for the **Standalone Parent Entity** across all 37 target metrics.
* **Columns & Null Statuses:** Identical layout to Sheet 1 (`0 CANDIDATES` vs. `REJECTED ALL` vs. `Final Value`).

### Sheet 3: `Candidate Audit Log`
* **Purpose:** Exhaustive pool of every candidate figure harvested by Layer 1 (`Consolidated`, `Standalone`, or `Unclear`).
* **Columns:** `Metric Target`, `Candidate Value`, `Entity Context`, `Source Type`, `Page #`, `Printed Page`, `Table / Section`, `Line Above Proof`, `Line Below Proof`, `Verbatim Text`, `Forensic Reasoning Log`.

### Sheet 4: `Coverage & Stats`
* **Purpose:** Executive summary table providing a side-by-side comparison of Consolidated vs. Standalone disclosures across all 37 target metrics.
* **Columns:** `Metric Name`, `Consolidated Disclosed?` (`YES/NO`), `Consolidated Value`, `Standalone Disclosed?` (`YES/NO`), `Standalone Value`, `Total Candidates Harvested`.

---

## 🚀 Execution & Command Reference

### Single Report Run (Example: Jindal Saw FY14)
```bash
python3 -m POC3.extractor \
  --pdf "/Users/fti/personal_work/nair/pdfs/Jindal Saw Ltd/14.pdf" \
  --company "Jindal Saw Ltd" \
  --year "FY14" \
  --model gemini-3.1-flash-lite \
  --concurrency 6 \
  --force
```
