"""
Excel exporter for POC3: Two-Stage Exhaustive Candidate Extraction & LLM Finalization Layer.

Generates a multi-sheet openpyxl workbook:
  - Sheet 1: Finalized Disclosures (winning values and locations)
  - Sheet 2: Candidate Audit Log (every candidate harvested across the PDF in Layer 1 and its details)
  - Sheet 3: Coverage & Stats (summary of metrics found/missing and token usage)
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import openpyxl
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

from POC3.metrics import METRIC_METADATA


HEADER_FILL = PatternFill(start_color="1F4E78", end_color="1F4E78", fill_type="solid")
HEADER_FONT = Font(name="Calibri", size=11, bold=True, color="FFFFFF")
DATA_FONT = Font(name="Calibri", size=11)
BOLD_FONT = Font(name="Calibri", size=11, bold=True)
THIN_BORDER = Border(
    left=Side(style="thin", color="D9D9D9"),
    right=Side(style="thin", color="D9D9D9"),
    top=Side(style="thin", color="D9D9D9"),
    bottom=Side(style="thin", color="D9D9D9"),
)
WRAP_ALIGN = Alignment(wrap_text=True, vertical="top")
TOP_ALIGN = Alignment(vertical="top")


def _style_headers(ws: openpyxl.worksheet.worksheet.Worksheet, row_idx: int = 1) -> None:
    for cell in ws[row_idx]:
        cell.fill = HEADER_FILL
        cell.font = HEADER_FONT
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        cell.border = THIN_BORDER
    ws.row_dimensions[row_idx].height = 26


def _auto_fit_columns(ws: openpyxl.worksheet.worksheet.Worksheet, max_len_cap: int = 50) -> None:
    for col in ws.columns:
        col_letter = get_column_letter(col[0].column)
        max_len = 0
        for cell in col:
            val_str = str(cell.value or "")
            if len(val_str) > max_len:
                max_len = min(len(val_str), max_len_cap)
        ws.column_dimensions[col_letter].width = max(max_len + 4, 12)


def export_to_excel(result: Any, output_path: Path | str) -> None:
    """Export an ExtractionResultPOC3 to an Excel workbook."""
    wb = openpyxl.Workbook()

    # ── Sheet 1: Finalized Disclosures ───────────────────────────────────────
    ws1 = wb.active
    ws1.title = "Finalized Disclosures"
    ws1.views.sheetView[0].showGridLines = True

    headers1 = [
        "Metric Target", "Final Value", "Entity Context", "Source Type",
        "Page #", "Printed Page", "Table / Section", "Standalone Fallback?",
        "Audit Log Summary", "Verbatim Source Text"
    ]
    ws1.append(headers1)
    _style_headers(ws1)

    for item in getattr(result, "finalized_metrics", []):
        val = item.get("final_value")
        win = item.get("winning_candidate") or {}
        audit_log = item.get("rejection_audit_log", [])
        audit_str = "\n".join(audit_log) if isinstance(audit_log, list) else str(audit_log)

        row = [
            item.get("metric_target", ""),
            val if val is not None else "NOT DISCLOSED",
            win.get("entity_context", "N/A"),
            win.get("source_type", "N/A"),
            win.get("page_number", ""),
            win.get("printed_page_number", ""),
            win.get("table_or_section", ""),
            "YES" if item.get("is_standalone_fallback_active") else "NO",
            audit_str,
            win.get("verbatim_source_text", ""),
        ]
        ws1.append(row)
        row_idx = ws1.max_row
        for col_idx in range(1, len(row) + 1):
            c = ws1.cell(row=row_idx, column=col_idx)
            c.font = BOLD_FONT if col_idx == 2 and val is not None else DATA_FONT
            c.border = THIN_BORDER
            c.alignment = WRAP_ALIGN if col_idx in (9, 10) else TOP_ALIGN

    _auto_fit_columns(ws1, max_len_cap=60)

    # ── Sheet 2: Candidate Audit Log ─────────────────────────────────────────
    ws2 = wb.create_sheet(title="Candidate Audit Log")
    ws2.views.sheetView[0].showGridLines = True

    headers2 = [
        "Metric Target", "Candidate Value", "Entity Context", "Source Type",
        "Page #", "Printed Page", "Table / Section",
        "Line Above Proof", "Line Below Proof",
        "Verbatim Text", "Forensic Reasoning Log"
    ]
    ws2.append(headers2)
    _style_headers(ws2)

    harvested = getattr(result, "harvested_candidates", {})
    for metric_name, cand_list in harvested.items():
        if not cand_list:
            row = [metric_name, "NO CANDIDATES FOUND", "", "", "", "", "", "", "", "", ""]
            ws2.append(row)
            continue
        for cand in cand_list:
            row = [
                cand.get("metric_target", metric_name),
                cand.get("current_year_value", ""),
                cand.get("entity_context", ""),
                cand.get("source_type", ""),
                cand.get("page_number", ""),
                cand.get("printed_page_number", ""),
                cand.get("table_or_section", ""),
                cand.get("page_verbatim_proof_above", ""),
                cand.get("page_verbatim_proof_below", ""),
                cand.get("verbatim_source_text", ""),
                cand.get("forensic_reasoning_log", ""),
            ]
            ws2.append(row)
            row_idx = ws2.max_row
            for col_idx in range(1, len(row) + 1):
                c = ws2.cell(row=row_idx, column=col_idx)
                c.font = DATA_FONT
                c.border = THIN_BORDER
                c.alignment = WRAP_ALIGN if col_idx in (8, 9, 10, 11) else TOP_ALIGN

    _auto_fit_columns(ws2, max_len_cap=50)

    # ── Sheet 3: Coverage & Stats ────────────────────────────────────────────
    ws3 = wb.create_sheet(title="Coverage & Stats")
    ws3.views.sheetView[0].showGridLines = True

    headers3 = ["Metric Name", "Disclosed?", "Candidates Harvested", "Final Winning Value"]
    ws3.append(headers3)
    _style_headers(ws3)

    coverage = getattr(result, "coverage", {})
    finalized_map = {m.get("metric_target"): m.get("final_value") for m in getattr(result, "finalized_metrics", [])}

    for m in METRIC_METADATA:
        mname = m["name"]
        disc = coverage.get(mname, False)
        cand_count = len(harvested.get(mname, []))
        fval = finalized_map.get(mname, "NOT DISCLOSED")

        row = [mname, "YES" if disc else "NO", cand_count, fval]
        ws3.append(row)
        row_idx = ws3.max_row
        for col_idx in range(1, len(row) + 1):
            c = ws3.cell(row=row_idx, column=col_idx)
            c.font = BOLD_FONT if col_idx in (2, 4) and disc else DATA_FONT
            c.border = THIN_BORDER
            c.alignment = TOP_ALIGN

    _auto_fit_columns(ws3, max_len_cap=40)

    wb.save(output_path)
