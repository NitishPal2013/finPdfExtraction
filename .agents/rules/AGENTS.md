# Financial Metrics Extractor: Project Scope & Goals

## 🎯 Overall Project Goal
The core objective of this project is to **successfully, reliably, and accurately extract target financial metrics** from any given financial PDF document (such as annual reports, quarterly filings, or financial statements) using Google's Gemini Vision API. 

The system aims to replicate the thoroughness and precision of a senior financial analyst, identifying not just values but the surrounding context, page numbers, years, periods, and whether the data is presented on a Consolidated or Standalone basis.

---

## 📊 Target Financial Metrics
The system currently targets 22+ financial metrics grouped into categories:
1. **Revenue & Earnings**: Operating Income, Adjusted Revenue, Adjusted Earnings, EBIT, EBITDA, Adjusted EBIT, Core Earnings, Normalized Earnings, Recurring Earnings, Adjusted EPS, Normalized EPS.
2. **Cash Flow & Balance Sheet**: Free Cash Flow, Funds from Operations (FFO), Distributable Cash Flow, Net Debt, Cash Earnings, Cash Loss.
3. **Currency & Growth**: Constant-Currency Revenues, Constant-Currency Revenue Growth, Constant-Currency Operating Expenses.
4. **GAAP Adjustments**: GAAP One-Time Adjusted, GAAP Adjusted.

---

## 📂 POC Architectures & Progress

To improve the extraction pipeline progressively without disrupting stable workflows, development is organized into separate Proof-of-Concept (POC) directories. Each directory contains its own localized documentation explaining its file structure, design decisions, and guidelines.

### Stable POCs
* **[POC2](file:///Users/fti/personal_work/nair/POC2/AGENTS.md)**: Per-metric targeted cached queries. Queries the Gemini File context cache 37 separate times concurrently (semaphore bounded) with an optional verification layer.
  * *Status*: Stable, deployed.
  * *For low-level file lists, commands, and local guidelines, see [POC2/AGENTS.md](file:///Users/fti/personal_work/nair/POC2/AGENTS.md).*
