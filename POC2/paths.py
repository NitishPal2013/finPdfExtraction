"""
Minimal path / identity helpers for POC2.

Unlike POC1, POC2 does NOT persist anything to disk under the project tree:
no rasterized image cache, no per-window JSON, no merged.json. The Streamlit
app feeds a temporary PDF directly to Gemini, the pipeline runs in memory,
and results are surfaced via download buttons / live UI.

The only "path" responsibility here is converting a company name + uploaded
filename into the display strings and FY label the prompt needs, plus a tiny
context manager for the temporary PDF on disk.
"""
from __future__ import annotations

import re
import tempfile
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator


@dataclass
class DocPaths2:
    """In-memory document identity for one POC2 run."""
    company_slug: str
    company_display: str
    year_stem: str
    fy_year: str
    pdf_path: Path  # temp file path; caller owns its lifecycle


def slugify(name: str) -> str:
    """Company name → directory-safe slug: lowercase alnum, separators stripped."""
    return re.sub(r"[^a-z0-9]+", "", name.lower())


def derive_year_from_filename(filename: str) -> str | None:
    """Return a 2-digit year stem from filename digits, or None if none present.

    Mirrors POC1.app.derive_year_from_filename so users get consistent behavior:
      'AR-2023.pdf' → '23';  '23.pdf' → '23';  'FY24.pdf' → '24'.
    """
    digits = re.sub(r"\D", "", Path(filename).stem)
    if not digits:
        return None
    return digits[-2:]


def normalize_fy_label(year_stem: str) -> str:
    """'23' → 'FY23 / March 31, 2023'  (Indian FY convention)."""
    digits = re.sub(r"\D", "", year_stem)
    if not digits:
        return f"FY{year_stem}"
    yy = digits[-2:]
    yyyy = digits if len(digits) == 4 else f"20{yy}"
    return f"FY{yy} / March 31, {yyyy}"


def derive_paths(
    pdf_path: Path,
    *,
    company_name: str,
    year_stem: str | None = None,
    fy_override: str | None = None,
) -> DocPaths2:
    """Build a DocPaths2 from a temp PDF + user-supplied company name."""
    if year_stem is None:
        year_stem = derive_year_from_filename(pdf_path.name) or "00"
    company_slug = slugify(company_name) or "company"
    company_display = company_name.strip() or company_slug.title()
    fy_year = fy_override or normalize_fy_label(year_stem)
    return DocPaths2(
        company_slug=company_slug,
        company_display=company_display,
        year_stem=year_stem,
        fy_year=fy_year,
        pdf_path=pdf_path,
    )


@contextmanager
def temp_pdf(content: bytes, *, suffix: str = ".pdf") -> Iterator[Path]:
    """Write `content` to a NamedTemporaryFile, yield its Path, delete on exit.

    Use as:
        with temp_pdf(uploaded.getvalue()) as p:
            run_pipeline(p)
    """
    tmp = tempfile.NamedTemporaryFile(suffix=suffix, delete=False)
    try:
        tmp.write(content)
        tmp.flush()
        tmp.close()
        yield Path(tmp.name)
    finally:
        try:
            Path(tmp.name).unlink(missing_ok=True)
        except OSError:
            pass
