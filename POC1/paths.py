"""
Shared path / identity derivation for the POC1 pipeline.

Input convention:
  pdfs/<company_slug>/<year_stem>.pdf       e.g. pdfs/jyotilabs/23.pdf

Auto-derived layout:
  pdfs/<company_slug>/<year_stem>_pages/    rasterized image cache (page_N.png)
  POC1/results/<company_slug>_<year_stem>/  per-document run outputs
      window_NN_pages_X-Y.json
      summary.json
      merged.json

Pass `--company-name` and/or `--fy-year` on either CLI to override the auto-derived
display strings (used as prompt placeholders).
"""
from __future__ import annotations

import argparse
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
RESULTS_ROOT = Path(__file__).resolve().parent / "results"


@dataclass
class DocPaths:
    pdf_path: Path
    company_slug: str
    company_display: str
    year_stem: str
    fy_year: str
    image_dir: Path
    output_dir: Path
    summary_path: Path
    merged_path: Path


def _slug_to_display(slug: str) -> str:
    return slug.replace("_", " ").replace("-", " ").title()


def _normalize_year(stem: str) -> tuple[str, str]:
    digits = re.sub(r"\D", "", stem)
    if not digits:
        raise SystemExit(f"Cannot derive year from PDF filename '{stem}' — no digits found")
    yy = digits[-2:]
    yyyy = digits if len(digits) == 4 else f"20{yy}"
    return yy, f"FY{yy} / March 31, {yyyy}"


def derive_paths(
    pdf_path: str | Path,
    *,
    company_override: str | None = None,
    fy_override: str | None = None,
) -> DocPaths:
    pdf_path = Path(pdf_path).expanduser().resolve()
    if not pdf_path.is_file() or pdf_path.suffix.lower() != ".pdf":
        raise SystemExit(f"PDF not found or not a .pdf: {pdf_path}")
    company_slug = pdf_path.parent.name
    company_display = company_override or _slug_to_display(company_slug)
    _, default_fy = _normalize_year(pdf_path.stem)
    fy_year = fy_override or default_fy
    image_dir = pdf_path.parent / f"{pdf_path.stem}_pages"
    output_dir = RESULTS_ROOT / f"{company_slug}_{pdf_path.stem}"
    return DocPaths(
        pdf_path=pdf_path,
        company_slug=company_slug,
        company_display=company_display,
        year_stem=pdf_path.stem,
        fy_year=fy_year,
        image_dir=image_dir,
        output_dir=output_dir,
        summary_path=output_dir / "summary.json",
        merged_path=output_dir / "merged.json",
    )


def ensure_images(pdf_path: Path, preferred_image_dir: Path) -> tuple[Path, int]:
    """Locate or rasterize page images. Returns (actual_image_dir, total_pages).

    Search order:
      1. preferred_image_dir (`<stem>_pages/`) — standard convention
      2. `<pdf_dir>/ss/` — legacy convention from earlier runs
    If neither has page_*.png files, invokes `lit screenshot <pdf> -o <preferred_image_dir>`
    via the @llamaindex/liteparse CLI (install with `npm i -g @llamaindex/liteparse`).
    """
    for cand in (preferred_image_dir, pdf_path.parent / "ss"):
        if cand.exists():
            pngs = sorted(cand.glob("page_*.png"))
            if pngs:
                print(f"[images] using existing cache: {cand} ({len(pngs)} pages)")
                return cand, len(pngs)

    if shutil.which("lit") is None:
        raise SystemExit(
            "No cached images and the `lit` CLI was not found on PATH. "
            "Install it with `npm i -g @llamaindex/liteparse`, or pre-render "
            "the PDF into page_*.png files at the expected image directory."
        )

    preferred_image_dir.mkdir(parents=True, exist_ok=True)
    print(f"[lit] screenshot {pdf_path} → {preferred_image_dir}")
    result = subprocess.run(
        ["lit", "screenshot", str(pdf_path), "-o", str(preferred_image_dir)],
        capture_output=True, text=True, check=False,
    )
    if result.stdout:
        print(result.stdout, end="")
    if result.returncode != 0:
        raise SystemExit(
            f"`lit screenshot` failed (exit {result.returncode}):\n{result.stderr}"
        )
    pngs = sorted(preferred_image_dir.glob("page_*.png"))
    if not pngs:
        raise SystemExit(
            f"`lit screenshot` produced no page_*.png files in {preferred_image_dir}. "
            f"stderr:\n{result.stderr}"
        )
    print(f"[lit] rasterized {len(pngs)} pages")
    return preferred_image_dir, len(pngs)


def add_common_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "pdf_path",
        help="Path to the source PDF (e.g. pdfs/jyotilabs/23.pdf). "
             "Company is derived from the parent directory; FY year from the filename.",
    )
    parser.add_argument(
        "--company-name",
        default=None,
        help="Override the company display name passed to the prompt "
             "(default: title-cased parent directory name).",
    )
    parser.add_argument(
        "--fy-year",
        default=None,
        help="Override the target FY label passed to the prompt "
             "(default: derived from PDF filename, e.g. '23.pdf' → 'FY23 / March 31, 2023').",
    )
