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

DEFAULT_MODEL = "gemini-3.1-flash-lite"
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
    finalized_consolidated_metrics: list[dict] = field(default_factory=list)
    finalized_standalone_metrics: list[dict] = field(default_factory=list)
    harvested_candidates: dict[str, list[dict]] = field(default_factory=dict)
    consolidated_coverage: dict[str, bool] = field(default_factory=dict)
    standalone_coverage: dict[str, bool] = field(default_factory=dict)
    totals: dict[str, Any] = field(default_factory=dict)

    @property
    def finalized_metrics(self) -> list[dict]:
        return self.finalized_consolidated_metrics

    @property
    def coverage(self) -> dict[str, bool]:
        return self.consolidated_coverage

    @property
    def found_count(self) -> int:
        return sum(1 for v in self.consolidated_coverage.values() if v)

    @property
    def missing_count(self) -> int:
        return sum(1 for v in self.consolidated_coverage.values() if not v)


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
        emit(f"[{label}] starting LLM call (attempt {attempt}) at {time.strftime('%X')}")
        try:
            response = await client.models.generate_content(
                model=model, contents=contents, config=config,
            )
            raw_text = getattr(response, "text", None) or ""
            parsed, usage = parse_fn(response)
            emit(f"[{label}] finished LLM call (attempt {attempt}) successfully in {time.time() - t0:.1f}s")
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
        t_acq = time.time()
        emit(f"[{label}] semaphore acquired at {time.strftime('%X')}, starting execution")
        try:
            candidates, usage, attempts, _ = await _call_with_retry(
                label=label, client=client, model=model,
                contents=prompt, config=config, parse_fn=_parse_candidate_response,
                emit=emit,
            )
        except NonRetryablePOC3Failure:
            return {"metric": metric["name"], "status": "error", "candidates": [], "usage": {}}

    elapsed = time.time() - t_acq
    emit(f"[{label}] Harvested {len(candidates)} candidate(s) in {elapsed:.1f}s total (semaphore-owned)")
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
    target_scope: str = "Consolidated",
) -> dict:
    label = f"L2[{target_scope[:4]}][{metric['name'][:18]}]"
    if not candidates:
        emit(f"[{label}] No candidates to finalize — skipping L2 API call")
        default_res = FinalizedMetricPOC3(
            metric_target=metric["name"],
            final_value=None,
            winning_candidate=None,
            rejection_audit_log=[f"[LAYER 1]: 0 {target_scope} candidate mentions found across entire document. Bypassed Layer 2 finalization."]
        ).model_dump()
        return {"metric": metric["name"], "status": "ok", "finalized": default_res, "usage": {}, "target_scope": target_scope}

    prompt = build_finalization_prompt(metric, candidates, target_scope=target_scope)
    config = types.GenerateContentConfig(
        cached_content=cache_name,
        response_mime_type="application/json",
        response_schema=FinalizedMetricPOC3.model_json_schema(),
        temperature=0.0,
        seed=42,
    )

    async with semaphore:
        t_acq = time.time()
        emit(f"[{label}] semaphore acquired at {time.strftime('%X')}, starting execution")
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

    elapsed = time.time() - t_acq
    val = finalized.get("final_value")
    win = finalized.get("winning_candidate")

    # Deterministic PBT vs. EBIT/EBITDA safety net check:
    if val is not None and win is not None:
        metric_name = metric["name"]
        verbatim = win.get("verbatim_source_text", "").lower()
        source = win.get("source_type", "")
        if any(m_type in metric_name for m_type in ["EBIT", "EBITDA"]):
            if source == "AUDITED_TABLE" and ("before exceptional" in verbatim or "before tax" in verbatim or "profit before tax" in verbatim) and not any(addback in verbatim for addback in ["depreciation", "interest", "finance", "amortisation"]):
                emit(f"[{label}] Deterministic rejection triggered: candidate verbatim '{win.get('verbatim_source_text')}' is statutory PBT, NOT EBIT/EBITDA!")
                finalized["final_value"] = None
                finalized["winning_candidate"] = None
                finalized["rejection_audit_log"].append(
                    f"[REJECTED via Deterministic Python Rule]: Rejected '{win.get('verbatim_source_text')}' on page {win.get('page_number')} as it represents Profit Before Tax (PBT) rather than {metric_name}."
                )
                val = None

    emit(f"[{label}] Finalized: {'FOUND (' + str(val) + ')' if val is not None else 'REJECTED ALL'} in {elapsed:.1f}s")
    return {
        "metric": metric["name"], "status": "ok",
        "finalized": finalized, "usage": usage, "elapsed_s": round(elapsed, 2),
        "target_scope": target_scope
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

        # Layer 2: LLM Finalization & Precision Selection (Dual-Scope: Consolidated & Standalone)
        emit("\n--- LAYER 2: LLM FINALIZATION & PRECISION SELECTION (DUAL-SCOPE) ---")
        l2_tasks = []
        for m in METRIC_METADATA:
            mname = m["name"]
            cands = harvested_candidates.get(mname, [])
            cons_cands = [c for c in cands if c.get("entity_context") in ("Consolidated", "Unclear")]
            std_cands = [c for c in cands if c.get("entity_context") in ("Standalone", "Unclear")]

            if cons_cands:
                l2_tasks.append(_finalize_one_metric(
                    metric=m, candidates=cons_cands, client=async_client, model=model,
                    cache_name=cache.name, semaphore=semaphore, emit=emit, target_scope="Consolidated"
                ))
            if std_cands:
                l2_tasks.append(_finalize_one_metric(
                    metric=m, candidates=std_cands, client=async_client, model=model,
                    cache_name=cache.name, semaphore=semaphore, emit=emit, target_scope="Standalone"
                ))

        l2_results = await asyncio.gather(*l2_tasks) if l2_tasks else []
        l2_cons_map = {res["metric"]: res for res in l2_results if res.get("target_scope") == "Consolidated"}
        l2_std_map = {res["metric"]: res for res in l2_results if res.get("target_scope") == "Standalone"}

        finalized_cons: list[dict] = []
        finalized_std: list[dict] = []
        cons_coverage: dict[str, bool] = {}
        std_coverage: dict[str, bool] = {}

        for m in METRIC_METADATA:
            mname = m["name"]
            # Consolidated slot
            if mname in l2_cons_map:
                f_cons = l2_cons_map[mname].get("finalized", {})
            else:
                f_cons = FinalizedMetricPOC3(
                    metric_target=mname, final_value=None, winning_candidate=None,
                    rejection_audit_log=["[LAYER 1]: 0 Consolidated candidate mentions found across entire document. Bypassed Layer 2 finalization."]
                ).model_dump()
            finalized_cons.append(f_cons)
            cons_coverage[mname] = (f_cons.get("final_value") is not None)

            # Standalone slot
            if mname in l2_std_map:
                f_std = l2_std_map[mname].get("finalized", {})
            else:
                f_std = FinalizedMetricPOC3(
                    metric_target=mname, final_value=None, winning_candidate=None,
                    rejection_audit_log=["[LAYER 1]: 0 Standalone candidate mentions found across entire document. Bypassed Layer 2 finalization."]
                ).model_dump()
            finalized_std.append(f_std)
            std_coverage[mname] = (f_std.get("final_value") is not None)

        # ── Deterministic Post-Processing Firewalls & Guards ─────────────────────
        def _normalize_val(v):
            if v is None:
                return None
            s = str(v).replace("%", "").replace(",", "").replace("₹", "").replace("Rs.", "").replace("Rs", "").strip().lower()
            for word in ["crore", "crores", "cr", "lakh", "lakhs", "lac", "lacs", "million", "millions", "mn", "billion", "billions", "bn", "inr", "usd"]:
                s = s.replace(word, "").strip()
            try:
                return float(s)
            except ValueError:
                return s

        def _apply_post_processing_guards(metrics: list[dict], scope_name: str):
            # Create a lookup map by metric target
            m_map = {m["metric_target"]: m for m in metrics}
            
            # 1. EBIT Margin vs EBITDA Margin Guard
            ebit_m = m_map.get("EBIT Margin")
            ebitda_m = m_map.get("EBITDA Margin")
            if ebit_m and ebitda_m:
                val1 = ebit_m.get("final_value")
                val2 = ebitda_m.get("final_value")
                val1_clean = _normalize_val(val1)
                val2_clean = _normalize_val(val2)
                if val1_clean is not None and val2_clean is not None and val1_clean == val2_clean:
                    emit(f"[{scope_name}] Duplicate Margin detected (EBIT Margin: {val1}, EBITDA Margin: {val2}). Applying EBIT/EBITDA Margin Guard.")
                    ebitda_m["final_value"] = None
                    ebitda_m["winning_candidate"] = None
                    ebitda_m["rejection_audit_log"].append(
                        f"[REJECTED via Deterministic EBIT/EBITDA Margin Guard]: EBITDA Margin cannot equal EBIT Margin (identical value '{val2}'). Rejected duplicate EBITDA Margin in favor of EBIT Margin."
                    )
            
            # 2. EBITDA vs Adjusted EBITDA Duplicate Firewall
            ebitda = m_map.get("EBITDA")
            adj_ebitda = m_map.get("Adjusted EBITDA")
            if ebitda and adj_ebitda:
                val_eb = ebitda.get("final_value")
                val_adj = adj_ebitda.get("final_value")
                val_eb_clean = _normalize_val(val_eb)
                val_adj_clean = _normalize_val(val_adj)
                if val_eb_clean is not None and val_adj_clean is not None and val_eb_clean == val_adj_clean:
                    win_adj = adj_ebitda.get("winning_candidate") or {}
                    verbatim = win_adj.get("verbatim_source_text", "").lower()
                    adj_keywords = ["exceptional", "adjustment", "one-time", "pro-forma", "adjusted", "normalized", "extraordinary"]
                    if not any(kw in verbatim for kw in adj_keywords):
                        emit(f"[{scope_name}] Duplicate EBITDA/Adjusted EBITDA detected (EBITDA: {val_eb}, Adjusted EBITDA: {val_adj}). Applying Adjusted EBITDA Duplicate Firewall.")
                        adj_ebitda["final_value"] = None
                        adj_ebitda["winning_candidate"] = None
                        adj_ebitda["rejection_audit_log"].append(
                            f"[REJECTED via Deterministic Adjusted EBITDA Duplicate Firewall]: Adjusted EBITDA equals unadjusted EBITDA ('{val_adj}') but verbatim text contains no adjustment keywords. Rejected duplicate Adjusted EBITDA."
                        )
            
            # 3. Consolidated CARO Cash Loss Firewall
            if scope_name == "Consolidated":
                for m_target in ["Cash Loss", "Cash Loss Incurrence Status"]:
                    m_item = m_map.get(m_target)
                    if m_item and m_item.get("final_value") is not None:
                        win = m_item.get("winning_candidate") or {}
                        verbatim = win.get("verbatim_source_text", "").lower()
                        ref_log = win.get("forensic_reasoning_log", "").lower()
                        if any(kw in verbatim or kw in ref_log for kw in ["caro", "clause", "xvii"]):
                            emit(f"[{scope_name}] Standalone CARO Cash Loss leaked into Consolidated for {m_target}. Applying CARO Firewall.")
                            m_item["final_value"] = None
                            m_item["winning_candidate"] = None
                            m_item["rejection_audit_log"].append(
                                f"[REJECTED via Deterministic CARO Firewall]: Standalone CARO Clause (xvii) details are not applicable to Consolidated Financial Statements."
                            )

        _apply_post_processing_guards(finalized_cons, "Consolidated")
        _apply_post_processing_guards(finalized_std, "Standalone")

        # Recalculate coverage cover dicts
        cons_coverage = {m["metric_target"]: (m.get("final_value") is not None) for m in finalized_cons}
        std_coverage = {m["metric_target"]: (m.get("final_value") is not None) for m in finalized_std}

        total_in = sum(r.get("usage", {}).get("input_tokens", 0) for r in l1_results + l2_results)
        total_out = sum(r.get("usage", {}).get("output_tokens", 0) for r in l1_results + l2_results)
        total_cached = sum(r.get("usage", {}).get("cached_tokens", 0) for r in l1_results + l2_results)

        totals = {
            "metrics_total": len(METRIC_METADATA),
            "metrics_found_cons": sum(1 for v in cons_coverage.values() if v),
            "metrics_found_std": sum(1 for v in std_coverage.values() if v),
            "tokens_in": total_in,
            "tokens_out": total_out,
            "tokens_cached_hits": total_cached,
            "elapsed_seconds": round(time.time() - t_total, 2),
        }

        emit("\n" + "=" * 70)
        emit("POC3 COMPLETED (DUAL-SCOPE)")
        emit(f"  Consolidated found: {totals['metrics_found_cons']}/{totals['metrics_total']}")
        emit(f"  Standalone found:   {totals['metrics_found_std']}/{totals['metrics_total']}")
        emit(f"  Tokens:             in={total_in:,} out={total_out:,} cached={total_cached:,}")
        emit(f"  Elapsed:            {totals['elapsed_seconds']}s")
        emit("=" * 70)

        return ExtractionResultPOC3(
            company_display=doc.company_display,
            fy_year=doc.fy_year,
            model=model,
            finalized_consolidated_metrics=finalized_cons,
            finalized_standalone_metrics=finalized_std,
            harvested_candidates=harvested_candidates,
            consolidated_coverage=cons_coverage,
            standalone_coverage=std_coverage,
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
        
        # Use out-suffix if provided, default to _POC3
        suffix = out_suffix if out_suffix else "_POC3"
        out_xlsx = pdf.parent / f"{pdf.stem}{suffix}.xlsx"
        out_json = pdf.parent / f"{pdf.stem}{suffix}.json"

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
    parser.add_argument("--out-suffix", required=False, default="_POC3", help="Suffix for output files (default: _POC3)")
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

        suffix = args.out_suffix if args.out_suffix else "_POC3"
        out_xlsx = pdf_p.parent / f"{pdf_p.stem}{suffix}.xlsx"
        out_json = pdf_p.parent / f"{pdf_p.stem}{suffix}.json"

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
