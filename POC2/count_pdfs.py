"""Count PDF files under a root, exposing case-sensitivity gotchas.

macOS's default filesystem is case-INSENSITIVE for lookups, but pathlib's
`glob("*.pdf")` matches case-SENSITIVELY — so `23.PDF` is skipped by a
lowercase-only glob. This script reports both so we can see the gap.
"""
from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path


def count_pdfs(root: Path) -> None:
    lower_only = sorted(root.rglob("*.pdf"))          # case-sensitive, lowercase
    case_insensitive = sorted(
        p for p in root.rglob("*") if p.is_file() and p.suffix.lower() == ".pdf"
    )

    # Tally the exact extension spellings present (.pdf, .PDF, .Pdf, …).
    ext_tally = Counter(p.suffix for p in case_insensitive)

    print(f"Root: {root}")
    print(f"  glob('*.pdf')  (lowercase only):  {len(lower_only)}")
    print(f"  case-insensitive (.pdf/.PDF/…):   {len(case_insensitive)}")
    print(f"  MISSED by lowercase glob:         {len(case_insensitive) - len(lower_only)}")
    print(f"  extension spellings: {dict(ext_tally)}")

    print("\nPer-company:")
    for cdir in sorted(p for p in root.iterdir() if p.is_dir()):
        lo = len(list(cdir.glob("*.pdf")))
        ci = len([p for p in cdir.iterdir()
                  if p.is_file() and p.suffix.lower() == ".pdf"])
        flag = "  <-- has uppercase .PDF" if ci != lo else ""
        print(f"  {cdir.name:<40} lower={lo:<3} all={ci:<3}{flag}")


if __name__ == "__main__":
    root = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("pdfs")
    count_pdfs(root)
