"""
POC3 Extractor: Two-Stage Exhaustive Candidate Extraction & LLM Finalization Layer.

Lifecycle (single run):
  1. Upload PDF to Gemini Files API and wait for ACTIVE.
  2. Create Context Cache (system instruction + uploaded PDF).
  3. Layer 1 (Candidate Harvesting): For each of the 37 metrics, dispatch concurrent bounded prompt to harvest ALL mentions across the document.
  4. Layer 2 (LLM Finalization & Precision Selection): For each metric with candidates, dispatch concurrent bounded prompt to verify physical page proofs, enforce Consolidated preference, rank by Audited Table > Notes > Narrative, and select the winner.
  5. Tear down cache and uploaded file in `finally`.
  6. Return in-memory ExtractionResultPOC3 and write Excel/JSON to disk.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import random
import sys as _sys
import time
import traceback
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Awaitable, Callable

import httpx
from google.genai import errors as gerrors
from google.genai import types
from pydantic import ValidationError

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in _sys.path:
    _sys.path.insert(0, str(_PROJECT_ROOT))

from POC3.gemini_client import make_async_client, make_sync_client
from POC3.metrics import METRIC_METADATA, MetricDef
from POC3.models import CandidateListResponse, FinalizedMetricPOC3, CandidateMetricPOC3
from POC3.paths import DocPaths3, derive_paths
from POC3.prompt import (
    build_candidate_extraction_prompt,
    build_finalization_prompt,
    build_system_instruction,
)

DEFAULT_MODEL = "gemini-2.5-flash"
BASE_DELAY = 2.0
MAX_DELAY = 60.0

RETRYABLE_NETWORK_ERRORS: tuple[type[BaseException], ...] = (
    gerrors.ServerError,
    httpx.RemoteProtocolError,
    httpx.ReadTimeout,
    httpx.WriteTimeout,
    httpx.ConnectTimeout,
    httpx.PoolTimeout,
    httpx.NetworkError,
    asyncio.TimeoutError,
    ConnectionError,
)


class _ResponseValidationError(Exception):
    """Raised when the model returned data we can't parse or trust."""


class NonRetryablePOC3Failure(SystemExit):
    """Raised on errors we won't keep retrying."""


def _is_retryable(exc: BaseException) -> bool:
    if isinstance(exc, _ResponseValidationError):
        return True
    if isinstance(exc, RETRYABLE_NETWORK_ERRORS):
        return True
    if isinstance(exc, gerrors.ClientError):
        status = getattr(exc, "code", None) or getattr(exc, "status_code", None)
        return status == 429
    return False


def _backoff_seconds(attempt: int) -> float:
    base = min(MAX_DELAY, BASE_DELAY * (2 ** (attempt - 1)))
    return base * (0.8 + 0.4 * random.random())


def _wait_for_active(sync_client, file_obj, *, timeout: float = 120.0, interval: float = 1.5):
    deadline = time.time() + timeout
    last_state = None
    while time.time() < deadline:
        refreshed = sync_client.files.get(name=file_obj.name)
        state = getattr(refreshed, "state", None)
        state_str = state.name if hasattr(state, "name") else str(state)
        last_state = state_str
        if state_str.endswith("ACTIVE"):
            return refreshed
        if state_str.endswith("FAILED"):
            raise RuntimeError(f"Files API reported state={state_str} for {file_obj.name}")
        time.sleep(interval)
    raise TimeoutError(f"File {file_obj.name} did not reach ACTIVE within {timeout}s (last state: {last_state})")


@dataclass
class ExtractionResultPOC3:
    company_display: str
    fy_year: str
    model: str
    finalized_metrics: list[dict] = field(default_factory=list)
    harvested_candidates: dict[str, list[dict]] = field(default_factory=dict)
    coverage: dict[str, bool] = field(default_factory=dict)
    totals: dict[str, Any] = field(default_factory=dict)

    @property
    def found_count(self) -> int:
        return sum(1 for v in self.coverage.values() if v)

    @property
    def missing_count(self) -> int:
        return sum(1 for v in self.coverage.values() if not v)


def _parse_candidate_response(response) -> tuple[list[dict], dict]:
    raw = getattr(response, "text", None) if response is not None else None
    if not raw:
        raise _ResponseValidationError("model returned an empty response body")
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as je:
        raise _ResponseValidationError(f"response was not valid JSON ({je}); preview: {raw[:300]!r}") from je
    if not isinstance(parsed, dict):
        raise _ResponseValidationError(f"response top-level is not an object: {type(parsed).__name__}")
    rows = parsed.get("candidates", [])
    if not isinstance(rows, list):
        raise _ResponseValidationError(f"`candidates` is not a list: {type(rows).__name__}")

    kept = []
    for row in rows:
        try:
            validated = CandidateMetricPOC3.model_validate(row)
            kept.append(validated.model_dump())
        except ValidationError:
            continue

    meta = getattr(response, "usage_metadata", None)
    usage = {
        "input_tokens": getattr(meta, "prompt_token_count", 0) or 0,
        "output_tokens": getattr(meta, "candidates_token_count", 0) or 0,
        "cached_tokens": getattr(meta, "cached_content_token_count", 0) or 0,
    }
    return kept, usage


def _parse_finalized_response(response) -> tuple[dict, dict]:
    raw = getattr(response, "text", None) if response is not None else None
    if not raw:
        raise _ResponseValidationError("empty finalization response")
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as je:
        raise _ResponseValidationError(f"finalization not JSON: {je}") from je
    try:
        v = FinalizedMetricPOC3.model_validate(parsed)
    except ValidationError as ve:
        raise _ResponseValidationError(f"finalization schema mismatch: {ve}") from ve

    meta = getattr(response, "usage_metadata", None)
    usage = {
        "input_tokens": getattr(meta, "prompt_token_count", 0) or 0,
        "output_tokens": getattr(meta, "candidates_token_count", 0) or 0,
        "cached_tokens": getattr(meta, "cached_content_token_count", 0) or 0,
    }
    return v.model_dump(), usage


async def _call_with_retry(
    *,
    label: str,
    client,
    model: str,
    contents: str,
    config: types.GenerateContentConfig,
    parse_fn: Callable[[Any], Any],
    emit: Callable[[str], None],
) -> tuple[Any, dict, int, str]:
    attempt = 0
    while True:
        attempt += 1
        t0 = time.time()
        try:
            response = await client.models.generate_content(
                model=model, contents=contents, config=config,
            )
            raw_text = getattr(response, "text", None) or ""
            parsed, usage = parse_fn(response)
            return parsed, usage, attempt, raw_text
        except Exception as e:
            elapsed = time.time() - t0
            err_type = type(e).__name__
            err_msg = (str(e) or repr(e))[:300]
            if not _is_retryable(e):
                msg = f"[{label}] non-retryable {err_type}: {err_msg}"
                emit(msg)
                raise NonRetryablePOC3Failure(msg) from e
            wait = _backoff_seconds(attempt)
            emit(f"[{label}] attempt {attempt} failed in {elapsed:.1f}s ({err_type}: {err_msg[:160]}); retry in {wait:.1f}s")
            await asyncio.sleep(wait)


async def _harvest_one_metric(
    *,
    metric: MetricDef,
    client,
    model: str,
    cache_name: str,
    semaphore: asyncio.Semaphore,
    emit: Callable[[str], None],
) -> dict:
    label = f"L1[{metric['name'][:20]}]"
    prompt = build_candidate_extraction_prompt(metric)
    config = types.GenerateContentConfig(
        cached_content=cache_name,
        response_mime_type="application/json",
        response_schema=CandidateListResponse.model_json_schema(),
        temperature=0.0,
        seed=42,
    )

    async with semaphore:
        t0 = time.time()
        try:
            candidates, usage, attempts, _ = await _call_with_retry(
                label=label, client=client, model=model,
                contents=prompt, config=config, parse_fn=_parse_candidate_response,
                emit=emit,
            )
        except NonRetryablePOC3Failure:
            return {"metric": metric["name"], "status": "error", "candidates": [], "usage": {}}

    elapsed = time.time() - t0
    emit(f"[{label}] Harvested {len(candidates)} candidate(s) in {elapsed:.1f}s")
    return {
        "metric": metric["name"], "status": "ok",
        "candidates": candidates, "usage": usage, "elapsed_s": round(elapsed, 2)
    }


async def _finalize_one_metric(
    *,
    metric: MetricDef,
    candidates: list[dict],
    client,
    model: str,
    cache_name: str,
    semaphore: asyncio.Semaphore,
    emit: Callable[[str], None],
) -> dict:
    label = f"L2[{metric['name'][:20]}]"
    if not candidates:
        emit(f"[{label}] No candidates to finalize — skipping L2 API call")
        default_res = FinalizedMetricPOC3(
            metric_target=metric["name"],
            final_value=None,
            winning_candidate=None,
            rejection_audit_log=["[LAYER 1]: Zero candidate mentions found across entire document."]
        ).model_dump()
        return {"metric": metric["name"], "status": "ok", "finalized": default_res, "usage": {}}

    prompt = build_finalization_prompt(metric, candidates)
    config = types.GenerateContentConfig(
        cached_content=cache_name,
        response_mime_type="application/json",
        response_schema=FinalizedMetricPOC3.model_json_schema(),
        temperature=0.0,
        seed=42,
    )

    async with semaphore:
        t0 = time.time()
        try:
            finalized, usage, attempts, _ = await _call_with_retry(
                label=label, client=client, model=model,
                contents=prompt, config=config, parse_fn=_parse_finalized_response,
                emit=emit,
            )
        except NonRetryablePOC3Failure:
            default_res = FinalizedMetricPOC3(
                metric_target=metric["name"],
                final_value=None,
                winning_candidate=None,
                rejection_audit_log=["[LAYER 2 ERROR]: Finalization call failed."]
            ).model_dump()
            return {"metric": metric["name"], "status": "error", "finalized": default_res, "usage": {}}

    elapsed = time.time() - t0
    val = finalized.get("final_value")
    emit(f"[{label}] Finalized: {'FOUND (' + str(val) + ')' if val is not None else 'REJECTED ALL'} in {elapsed:.1f}s")
    return {
        "metric": metric["name"], "status": "ok",
        "finalized": finalized, "usage": usage, "elapsed_s": round(elapsed, 2)
    }


async def run_extraction(
    doc: DocPaths3,
    *,
    model: str = DEFAULT_MODEL,
    concurrency: int = 4,
    cache_ttl_seconds: int = 7200,
    progress_callback: Callable[[str], None] | None = None,
) -> ExtractionResultPOC3:
    emit: Callable[[str], None] = progress_callback or print
    async_client = make_async_client()
    sync_client = make_sync_client()

    system_instruction = build_system_instruction(doc.company_display, doc.fy_year)
    uploaded_file = None
    cache = None
    t_total = time.time()

    emit("=" * 70)
    emit(f"POC3 (Two-Stage Candidate Harvesting & Finalization) — {model}")
    emit(f"PDF:        {doc.pdf_path}")
    emit(f"Company:    {doc.company_display}   |   FY: {doc.fy_year}")
    emit(f"Metrics:    {len(METRIC_METADATA)}  |  Concurrency: {concurrency}")
    emit("=" * 70)

    try:
        t_up = time.time()
        emit(f"[upload] sending {doc.pdf_path.name} to Gemini Files API…")
        uploaded_file = sync_client.files.upload(file=str(doc.pdf_path))
        emit(f"[upload] done in {time.time() - t_up:.1f}s — {uploaded_file.name}")

        t_active = time.time()
        uploaded_file = _wait_for_active(sync_client, uploaded_file)
        emit(f"[upload] file ACTIVE in {time.time() - t_active:.1f}s")

        t_cache = time.time()
        emit(f"[cache] creating ttl={cache_ttl_seconds}s …")
        cache = sync_client.caches.create(
            model=model,
            config=types.CreateCachedContentConfig(
                contents=[uploaded_file],
                system_instruction=system_instruction,
                ttl=f"{cache_ttl_seconds}s",
            ),
        )
        emit(f"[cache] ready in {time.time() - t_cache:.1f}s — {cache.name}")

        semaphore = asyncio.Semaphore(concurrency)

        # Layer 1: Candidate Harvesting
        emit("\n--- LAYER 1: EXHAUSTIVE CANDIDATE HARVESTING ---")
        l1_tasks = [
            _harvest_one_metric(
                metric=m, client=async_client, model=model,
                cache_name=cache.name, semaphore=semaphore, emit=emit,
            )
            for m in METRIC_METADATA
        ]
        l1_results = await asyncio.gather(*l1_tasks)

        harvested_candidates: dict[str, list[dict]] = {}
        for res in l1_results:
            harvested_candidates[res["metric"]] = res.get("candidates", [])

        # Layer 2: LLM Finalization & Precision Selection
        emit("\n--- LAYER 2: LLM FINALIZATION & PRECISION SELECTION ---")
        l2_tasks = [
            _finalize_one_metric(
                metric=m, candidates=harvested_candidates.get(m["name"], []),
                client=async_client, model=model,
                cache_name=cache.name, semaphore=semaphore, emit=emit,
            )
            for m in METRIC_METADATA
        ]
        l2_results = await asyncio.gather(*l2_tasks)

        finalized_metrics: list[dict] = []
        coverage: dict[str, bool] = {}
        for res in l2_results:
            f_obj = res.get("finalized", {})
            finalized_metrics.append(f_obj)
            val = f_obj.get("final_value")
            coverage[f_obj.get("metric_target", res["metric"])] = (val is not None)

        total_in = sum(r.get("usage", {}).get("input_tokens", 0) for r in l1_results + l2_results)
        total_out = sum(r.get("usage", {}).get("output_tokens", 0) for r in l1_results + l2_results)
        total_cached = sum(r.get("usage", {}).get("cached_tokens", 0) for r in l1_results + l2_results)

        totals = {
            "metrics_total": len(METRIC_METADATA),
            "metrics_found": sum(1 for v in coverage.values() if v),
            "tokens_in": total_in,
            "tokens_out": total_out,
            "tokens_cached_hits": total_cached,
            "elapsed_seconds": round(time.time() - t_total, 2),
        }

        emit("\n" + "=" * 70)
        emit("POC3 COMPLETED")
        emit(f"  Metrics found:   {totals['metrics_found']}/{totals['metrics_total']}")
        emit(f"  Tokens:          in={total_in:,} out={total_out:,} cached={total_cached:,}")
        emit(f"  Elapsed:         {totals['elapsed_seconds']}s")
        emit("=" * 70)

        return ExtractionResultPOC3(
            company_display=doc.company_display,
            fy_year=doc.fy_year,
            model=model,
            finalized_metrics=finalized_metrics,
            harvested_candidates=harvested_candidates,
            coverage=coverage,
            totals=totals,
        )

    finally:
        if cache is not None:
            try:
                sync_client.caches.delete(name=cache.name)
                emit(f"[cleanup] cache deleted: {cache.name}")
            except Exception as e:
                emit(f"[cleanup] cache delete failed: {e!r}")
        if uploaded_file is not None:
            try:
                sync_client.files.delete(name=uploaded_file.name)
                emit(f"[cleanup] uploaded file deleted: {uploaded_file.name}")
            except Exception as e:
                emit(f"[cleanup] file delete failed: {e!r}")


async def run_extraction_company(
    company_dir: Path | str,
    *,
    model: str = DEFAULT_MODEL,
    concurrency: int = 4,
    force: bool = False,
) -> list[dict]:
    """Run POC3 extraction over all annual report PDFs in a company directory."""
    company_dir = Path(company_dir).resolve()
    if not company_dir.is_dir():
        raise NotADirectoryError(f"Not a directory: {company_dir}")

    company_name = company_dir.name
    pdfs = sorted([p for p in company_dir.glob("*.pdf") if not p.name.endswith("_audit_pages.pdf")])
    print(f"[{company_name}] Starting batch extraction for {len(pdfs)} PDF(s) in {company_dir}")

    outcomes = []
    for pdf in pdfs:
        t0 = time.time()
        out_xlsx = pdf.parent / f"{pdf.stem}_POC3.xlsx"
        out_json = pdf.parent / f"{pdf.stem}_POC3.json"

        if out_xlsx.exists() and not force:
            print(f"[{company_name}] {pdf.name} -> already exists ({out_xlsx.name}), skipping.")
            outcomes.append({"pdf": pdf.name, "status": "skipped_exists"})
            continue

        print(f"\n{'='*70}\n[{company_name}] Processing {pdf.name} (Model: {model})...\n{'='*70}")
        try:
            doc_paths = derive_paths(pdf, company_name=company_name)
            result = await run_extraction(doc_paths, model=model, concurrency=concurrency)

            from POC3.excel_export import export_to_excel
            export_to_excel(result, out_xlsx)

            with open(out_json, "w", encoding="utf-8") as f:
                json.dump({
                    "company": result.company_display,
                    "fy_year": result.fy_year,
                    "model": result.model,
                    "totals": result.totals,
                    "finalized_metrics": result.finalized_metrics,
                    "harvested_candidates": result.harvested_candidates,
                }, f, indent=2)

            elapsed = round(time.time() - t0, 1)
            print(f"[{company_name}] Finished {pdf.name} in {elapsed}s -> saved {out_xlsx.name}")
            outcomes.append({"pdf": pdf.name, "status": "ok", "elapsed_s": elapsed, "found": result.totals.get("metrics_found", 0)})
        except Exception as e:
            elapsed = round(time.time() - t0, 1)
            print(f"[{company_name}] FAILED {pdf.name} after {elapsed}s: {type(e).__name__}: {e}")
            outcomes.append({"pdf": pdf.name, "status": "error", "error": str(e), "elapsed_s": elapsed})

    print(f"\n[{company_name}] Batch Complete! Outcomes:")
    for o in outcomes:
        print(f"  - {o['pdf']}: {o['status']} ({o.get('found', '-')}/37 metrics found) [{o.get('elapsed_s', '-')}s]")
    return outcomes


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run POC3 Two-Stage Extractor on a PDF or Directory.")
    parser.add_argument("--pdf", required=False, help="Path to PDF file")
    parser.add_argument("--company-dir", required=False, help="Path to company folder containing PDFs")
    parser.add_argument("--company", required=False, help="Company display name")
    parser.add_argument("--year", required=False, help="Target FY year (e.g. FY14)")
    parser.add_argument("--model", default=DEFAULT_MODEL, help="Gemini model name")
    parser.add_argument("--concurrency", type=int, default=4, help="Semaphore concurrency limit")
    parser.add_argument("--force", action="store_true", help="Overwrite existing workbooks")
    args = parser.parse_args()

    if args.company_dir:
        asyncio.run(run_extraction_company(args.company_dir, model=args.model, concurrency=args.concurrency, force=args.force))
    elif args.pdf:
        if not args.company or not args.year:
            parser.error("--company and --year are required when using --pdf")
        pdf_p = Path(args.pdf).resolve()
        if not pdf_p.exists():
            print(f"Error: PDF not found at {pdf_p}")
            _sys.exit(1)

        doc_paths = derive_paths(pdf_p, company_name=args.company, fy_override=args.year)
        result = asyncio.run(run_extraction(doc_paths, model=args.model, concurrency=args.concurrency))

        out_xlsx = pdf_p.parent / f"{pdf_p.stem}_POC3.xlsx"
        out_json = pdf_p.parent / f"{pdf_p.stem}_POC3.json"

        try:
            from POC3.excel_export import export_to_excel
            export_to_excel(result, out_xlsx)
            print(f"Excel saved to {out_xlsx}")
        except Exception as e:
            print(f"Failed to save Excel: {e}")

        with open(out_json, "w", encoding="utf-8") as f:
            json.dump({
                "company": result.company_display,
                "fy_year": result.fy_year,
                "model": result.model,
                "totals": result.totals,
                "finalized_metrics": result.finalized_metrics,
                "harvested_candidates": result.harvested_candidates,
            }, f, indent=2)
        print(f"JSON saved to {out_json}")
    else:
        parser.error("Either --pdf or --company-dir must be specified")
