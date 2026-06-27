"""
Merge per-PDF extraction results into a single tick/cross report.

WHAT IT DOES
------------
After the scale run has written a per-year workbook next to each PDF
(`pdfs/<Company>/13.xlsx`, `14.xlsx`, …), this script reads them back and
produces ONE summary workbook:

  • one sheet per company  — rows = years, columns = the 37 metrics
  • one "MEGA" sheet       — every company stacked (Company | Year | m1…m37)

Each cell is a green ✓ or a red ✗:
  ✓  the metric has a row in that year's "Extractions" sheet with verified=True
  ✗  everything else (not found, or found but verification rejected it)

It reads ONLY the saved .xlsx files — no API calls, no cost. Re-run it as
often as you like; it always reflects whatever workbooks currently exist.

USAGE
-----
    python POC2/merge_results.py                       # root=pdfs, out=pdfs/merged_results.xlsx
    python POC2/merge_results.py pdfs                  # custom root
    python POC2/merge_results.py pdfs report.xlsx      # custom root + output path

The output file is written at the ROOT level (never inside a company folder),
so re-running never picks the report up as if it were a year workbook.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import pandas as pd
from openpyxl.styles import Font

# Robust path bootstrap so `python POC2/merge_results.py` finds the package.
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from POC2.metrics import METRIC_METADATA

# The 37 metric names, in their canonical order — these are the table columns.
METRIC_NAMES: list[str] = [m["name"] for m in METRIC_METADATA]

TICK = "✓"
CROSS = "✗"

_GREEN = Font(color="1A7F37", bold=True)   # ✓
_RED = Font(color="C0392B")                # ✗


# ---------------------------------------------------------------------------
# Reading one year's workbook
# ---------------------------------------------------------------------------

def _is_verified(value) -> bool:
    """Coerce the 'verified' cell (bool, or 'True'/'False' string) to a bool."""
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() == "true"
    return False


def _year_label(xlsx_path: Path) -> str:
    """Best FY label for a year workbook.

    Prefers the exact 'FY year' written into the Summary sheet at extraction
    time; falls back to the filename stem (e.g. '13' → 'FY13').
    """
    try:
        sdf = pd.read_excel(xlsx_path, sheet_name="Summary", header=0)
        kv = dict(zip(sdf.iloc[:, 0].astype(str), sdf.iloc[:, 1]))
        fy = kv.get("FY year")
        if isinstance(fy, str) and fy.strip():
            return fy.strip()
    except Exception:  # noqa: BLE001 — Summary missing/odd shape → fall back
        pass
    digits = re.sub(r"\D", "", xlsx_path.stem)
    return f"FY{digits[-2:]}" if digits else xlsx_path.stem


def _verified_metrics(xlsx_path: Path) -> tuple[set[str], bool]:
    """Return (set of metric_targets with verified=True, had_verified_column).

    `had_verified_column` is False when the workbook carries no verification
    data at all — used to warn that the run was likely do_verify=False.
    """
    try:
        df = pd.read_excel(xlsx_path, sheet_name="Extractions", header=0)
    except Exception as e:  # noqa: BLE001
        print(f"    ! could not read Extractions from {xlsx_path.name}: {e}")
        return set(), False

    if df.empty or "metric_target" not in df.columns:
        return set(), ("verified" in df.columns)

    had_verified = "verified" in df.columns and df["verified"].notna().any()
    found: set[str] = set()
    if "verified" in df.columns:
        for _, row in df.iterrows():
            if _is_verified(row.get("verified")):
                found.add(str(row.get("metric_target", "")).strip())
    return found, had_verified


# ---------------------------------------------------------------------------
# Building the tables
# ---------------------------------------------------------------------------

def _row_for_year(verified: set[str]) -> dict[str, str]:
    """One table row: ✓/✗ per metric, in canonical column order."""
    return {name: (TICK if name in verified else CROSS) for name in METRIC_NAMES}


def _sorted_year_files(company_dir: Path) -> list[Path]:
    """Year workbooks in chronological order (sorted by the numeric stem)."""
    def key(p: Path) -> tuple[int, str]:
        digits = re.sub(r"\D", "", p.stem)
        return (int(digits) if digits else 9999, p.stem)
    return sorted(company_dir.glob("*.xlsx"), key=key)


def build_company_table(company_dir: Path) -> pd.DataFrame:
    """Per-company table: one row per year, columns = Year + 37 metrics."""
    rows: list[dict] = []
    for xlsx in _sorted_year_files(company_dir):
        verified, had_verified = _verified_metrics(xlsx)
        if not had_verified:
            print(f"    ! {company_dir.name}/{xlsx.name}: no verification data "
                  f"(was do_verify=True?) — all crosses for this year")
        rows.append({"Year": _year_label(xlsx), **_row_for_year(verified)})
    return pd.DataFrame(rows, columns=["Year", *METRIC_NAMES])


# ---------------------------------------------------------------------------
# Styling — colour the ✓ green and ✗ red after pandas writes the cells
# ---------------------------------------------------------------------------

def _colourise(writer: pd.ExcelWriter) -> None:
    for ws in writer.book.worksheets:
        for row in ws.iter_rows():
            for cell in row:
                if cell.value == TICK:
                    cell.font = _GREEN
                elif cell.value == CROSS:
                    cell.font = _RED


def _safe_sheet_name(name: str, used: set[str]) -> str:
    """Excel sheet names: ≤31 chars, no []:*?/\\, and unique."""
    clean = re.sub(r"[\[\]:*?/\\]", " ", name).strip()[:31] or "Sheet"
    candidate, n = clean, 1
    while candidate.lower() in used:
        suffix = f" ({n})"
        candidate = clean[:31 - len(suffix)] + suffix
        n += 1
    used.add(candidate.lower())
    return candidate


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def merge_results(pdfs_root: Path, out_path: Path) -> None:
    company_dirs = sorted(p for p in pdfs_root.iterdir() if p.is_dir())
    if not company_dirs:
        print(f"No company folders under {pdfs_root}")
        return

    print(f"Merging {len(company_dirs)} companies under {pdfs_root} …")

    per_company: dict[str, pd.DataFrame] = {}
    mega_rows: list[dict] = []

    for cdir in company_dirs:
        table = build_company_table(cdir)
        if table.empty:
            print(f"  {cdir.name}: no .xlsx year files — skipped")
            continue
        per_company[cdir.name] = table
        n_years = len(table)
        n_ticks = int((table[METRIC_NAMES] == TICK).to_numpy().sum())
        print(f"  {cdir.name:<40} {n_years} year(s), {n_ticks} ✓ total")
        for _, r in table.iterrows():
            mega_rows.append({"Company": cdir.name, **r.to_dict()})

    if not per_company:
        print("Nothing to write — no year workbooks found.")
        return

    mega_df = pd.DataFrame(mega_rows, columns=["Company", "Year", *METRIC_NAMES])

    with pd.ExcelWriter(out_path, engine="openpyxl") as writer:
        mega_df.to_excel(writer, sheet_name="MEGA", index=False)
        used = {"mega"}
        for company, table in per_company.items():
            table.to_excel(writer, sheet_name=_safe_sheet_name(company, used),
                           index=False)
        _colourise(writer)

    print(f"\nWrote {out_path}")
    print(f"  MEGA sheet: {len(mega_df)} rows ({len(per_company)} companies)")
    print(f"  + one sheet per company")


if __name__ == "__main__":
    root = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("pdfs")
    out = Path(sys.argv[2]) if len(sys.argv) > 2 else root / "merged_results.xlsx"
    if not root.is_dir():
        sys.exit(f"Not a directory: {root}")
    merge_results(root, out)
