"""
Merge + dedupe per-window extractions for one document into a single JSON.

Usage:
  python -m POC1.merge <pdf_path> [--company-name X] [--fy-year Y]

Reads window_*.json from the per-document results directory derived from the
PDF path (POC1/results/<company>_<year>/) and writes merged.json alongside.

Dedup key: (metric_target, entity_context, page_number, normalized_value).
Normalization strips whitespace and currency noise (₹/Rs./Rupees, Crore/Cr) so
"₹315.9 Crore" and "315.9" on the same page collapse. We track which windows
contributed each dedup'd metric in a `sources` list for auditability.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import get_args

from .models import MetricTarget
from .paths import add_common_args, derive_paths

# Authoritative list of metric_targets from the prompt15 schema. The coverage
# map below iterates in this order so the output has a stable, predictable
# shape — easy to eyeball what the pipeline is missing.
ALL_METRIC_TARGETS: tuple[str, ...] = get_args(MetricTarget)


def normalize_value(v: object) -> str:
    if v is None:
        return ""
    s = str(v).strip().lower()
    # Drop currency prefixes/suffixes we don't care about for identity
    s = re.sub(r"[₹$€£]", "", s)
    s = re.sub(r"\b(rs\.?|rupees?|inr|usd)\b", "", s)
    s = re.sub(r"\b(crore|cr\.?|lakh|lakhs|mn|million|bn|billion)\b", "", s)
    # Collapse whitespace and drop trailing punctuation
    s = re.sub(r"\s+", " ", s).strip(" .,:;")
    return s


def dedup_key(m: dict) -> tuple:
    return (
        (m.get("metric_target") or "").strip(),
        (m.get("entity_context") or "").strip(),
        m.get("page_number"),
        normalize_value(m.get("current_year_value")),
    )


# Preference order for entity_context. Consolidated wins; if a metric_target
# has no Consolidated rows we fall back to Standalone; Unclear is last resort.
ENTITY_PRIORITY = ["Consolidated", "Standalone", "Unclear"]


def filter_to_canonical(metrics: list[dict]) -> tuple[list[dict], dict]:
    """For each metric_target, keep only rows of the best available entity_context,
    then collapse page-level duplicates (same normalized value → one row,
    sources merged)."""
    by_target: dict[str, list[dict]] = {}
    for m in metrics:
        by_target.setdefault((m.get("metric_target") or "").strip(), []).append(m)

    canonical: list[dict] = []
    stats = {"targets_total": 0, "targets_with_consolidated": 0,
             "targets_fallback_standalone": 0, "targets_fallback_unclear": 0,
             "rows_dropped_by_context_filter": 0}

    for target, rows in by_target.items():
        if not target:
            continue
        stats["targets_total"] += 1
        # Pick preferred entity context actually present for this target.
        contexts_present = {(r.get("entity_context") or "").strip() for r in rows}
        chosen_ctx = next((c for c in ENTITY_PRIORITY if c in contexts_present), None)
        if chosen_ctx == "Consolidated":
            stats["targets_with_consolidated"] += 1
        elif chosen_ctx == "Standalone":
            stats["targets_fallback_standalone"] += 1
        elif chosen_ctx == "Unclear":
            stats["targets_fallback_unclear"] += 1
        else:
            continue  # no rows with a recognised context — skip

        kept = [r for r in rows if (r.get("entity_context") or "").strip() == chosen_ctx]
        stats["rows_dropped_by_context_filter"] += len(rows) - len(kept)

        # Collapse page-level duplicates: same (target, normalized_value) → 1 row
        # but merge pages + anchors + sources so we don't silently lose evidence.
        by_value: dict[str, dict] = {}
        for r in kept:
            vk = normalize_value(r.get("current_year_value"))
            if vk in by_value:
                existing = by_value[vk]
                existing.setdefault("pages", []).append(r.get("page_number"))
                existing.setdefault("alt_anchors", []).append(r.get("verbatim_source_text"))
                existing.setdefault("sources", []).extend(r.get("sources", []))
            else:
                clone = dict(r)
                clone["pages"] = [r.get("page_number")]
                clone["alt_anchors"] = []
                by_value[vk] = clone

        for v in by_value.values():
            # Dedup sources list while keeping order-ish
            seen = set(); uniq_src = []
            for s in v.get("sources", []):
                if s not in seen:
                    seen.add(s); uniq_src.append(s)
            v["sources"] = uniq_src
            canonical.append(v)

    canonical.sort(key=lambda m: (str(m.get("metric_target", "")),
                                  str(m.get("current_year_value", ""))))
    return canonical, stats


def compute_coverage(canonical: list[dict]) -> dict:
    """For every metric_target declared in the prompt15 schema, record whether
    the canonical list contains it. Lets the caller see at a glance what the
    pipeline found and — more importantly — what it did NOT find."""
    found_targets = {(m.get("metric_target") or "").strip() for m in canonical}
    # Preserve schema order so the map is stable across runs
    coverage = {target: (target in found_targets) for target in ALL_METRIC_TARGETS}
    return {
        "total_targets": len(ALL_METRIC_TARGETS),
        "found_count": sum(1 for v in coverage.values() if v),
        "missing_count": sum(1 for v in coverage.values() if not v),
        "missing_targets": [t for t, v in coverage.items() if not v],
        "coverage": coverage,
    }


def merge_for_doc(results_dir: Path, out_path: Path) -> dict:
    files = sorted(results_dir.glob("window_*.json"))
    if not files:
        raise SystemExit(f"No window files in {results_dir} — run `python -m POC1.run_simple <pdf>` first.")

    deduped: dict[tuple, dict] = {}
    raw_total = 0
    per_window_counts: list[dict] = []
    failures: list[dict] = []
    total_in = 0
    total_out = 0
    total_elapsed = 0.0
    model_seen: set[str] = set()

    for f in files:
        rec = json.load(open(f))
        model_seen.add(rec.get("model", "unknown"))
        status = rec.get("status")
        if status != "ok":
            failures.append({"file": f.name, "status": status, "error": rec.get("error")})
            per_window_counts.append({
                "file": f.name, "status": status,
                "start_page": rec.get("start_page"), "end_page": rec.get("end_page"),
                "num_extractions": 0,
            })
            continue

        usage = rec.get("usage", {})
        total_in += usage.get("input_tokens", 0) or 0
        total_out += usage.get("output_tokens", 0) or 0
        total_elapsed += rec.get("elapsed_s", 0) or 0

        em = rec.get("response", {}).get("extracted_metrics", []) or []
        raw_total += len(em)
        per_window_counts.append({
            "file": f.name, "status": status,
            "start_page": rec.get("start_page"), "end_page": rec.get("end_page"),
            "num_extractions": len(em),
        })

        src_label = f.name
        for m in em:
            k = dedup_key(m)
            if k in deduped:
                existing = deduped[k]
                existing.setdefault("sources", []).append(src_label)
            else:
                merged = dict(m)
                merged["sources"] = [src_label]
                deduped[k] = merged

    # Sort deterministically: by page, then metric_target, then value
    merged_list = sorted(
        deduped.values(),
        key=lambda m: (m.get("page_number") or 0, str(m.get("metric_target", "")), str(m.get("current_year_value", ""))),
    )

    canonical, canonical_stats = filter_to_canonical(merged_list)
    coverage = compute_coverage(canonical)

    result = {
        "model": sorted(model_seen)[0] if len(model_seen) == 1 else sorted(model_seen),
        "source_dir": str(results_dir),
        "windows_processed": len(files),
        "windows_failed": len(failures),
        "raw_metric_count_before_dedup": raw_total,
        "unique_metric_count_after_dedup": len(merged_list),
        "duplicates_collapsed": raw_total - len(merged_list),
        "canonical_metric_count": len(canonical),
        "canonical_filter_stats": canonical_stats,
        "target_coverage": coverage,
        "tokens_total": {"input": total_in, "output": total_out},
        "total_gen_seconds": round(total_elapsed, 2),
        "per_window": per_window_counts,
        "failures": failures,
        "metrics": merged_list,
        "canonical_metrics": canonical,
    }

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)

    print("=" * 70)
    print("MERGED")
    print("=" * 70)
    print(f"  Model:                  {result['model']}")
    print(f"  Windows:                {result['windows_processed']}  (failed: {result['windows_failed']})")
    print(f"  Raw metrics:            {result['raw_metric_count_before_dedup']}")
    print(f"  Unique after dedup:     {result['unique_metric_count_after_dedup']}")
    print(f"  Duplicates collapsed:   {result['duplicates_collapsed']}")
    print(f"  Canonical (Consol/SA):  {result['canonical_metric_count']}")
    print(f"    targets total:          {canonical_stats['targets_total']}")
    print(f"    → Consolidated kept:    {canonical_stats['targets_with_consolidated']}")
    print(f"    → Standalone fallback:  {canonical_stats['targets_fallback_standalone']}")
    print(f"    → Unclear fallback:     {canonical_stats['targets_fallback_unclear']}")
    print(f"    rows dropped by filter: {canonical_stats['rows_dropped_by_context_filter']}")
    print(f"  Target coverage:        {coverage['found_count']}/{coverage['total_targets']} found "
          f"({coverage['missing_count']} missing)")
    print(f"  Tokens in/out:          {total_in:,} / {total_out:,}")
    print(f"  Total gen seconds:      {total_elapsed:.1f}")
    print(f"  Written:                {out_path}")
    return result


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Merge + dedupe per-window extractions for one document."
    )
    add_common_args(parser)
    args = parser.parse_args()
    doc = derive_paths(
        args.pdf_path,
        company_override=args.company_name,
        fy_override=args.fy_year,
    )
    merge_for_doc(doc.output_dir, doc.merged_path)


if __name__ == "__main__":
    main()
