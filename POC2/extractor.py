"""
POC2 extractor: per-metric extraction against a cached PDF.

Lifecycle (single run):
  1. Upload the user's PDF to the Gemini Files API.
  2. Create explicit cached content: system instruction + the uploaded PDF.
  3. For each of the 37 metrics, dispatch a targeted prompt with
     `cached_content=cache.name`. Concurrent with bounded semaphore.
  4. (Optional) Verification layer — false-positive audit: for each found
     row, ask the model whether the finding is genuinely the target metric
     (by its definition) and the value is right, against the same cache.
  5. Tear down the cache and uploaded file in `finally` — POC2 does NOT
     persist artifacts to disk under the project tree.

Retry policy mirrors POC1.run: infinite retries on transient errors
(network, 5xx, 429, parse glitches), abort immediately on non-retryable
errors (auth, 4xx other than 429, code bugs).

Progress is emitted via an optional `progress_callback` injected by the
caller (Streamlit hands in `st.status.write`). When the callback is omitted
(CLI runs), events fall back to plain print().
"""
from __future__ import annotations

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

import pandas

# Robust path bootstrap — see POC1.run for the same idiom. Lets us import
# `POC2.*` whether we were started as a package, a module, or Streamlit's
# auto-loader.
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in _sys.path:
    _sys.path.insert(0, str(_PROJECT_ROOT))

from POC2.gemini_client import make_async_client, make_sync_client
from POC2.metrics import METRIC_METADATA, MetricDef
from POC2.models import Prompt2Response, VerificationResponse
from POC2.paths import DocPaths2, derive_paths
from POC2.prompt import (
    build_metric_prompt,
    build_system_instruction,
    build_verification_prompt,
)


# Default model. Streamlit UI offers a picker; CLI uses this fallback.
DEFAULT_MODEL = "gemini-3.1-flash-lite"

# Same display-name → API-id mapping POC1 exposes. Caching is supported on
# Gemini 2.5+ flash/pro lines; flash-lite caching exists on later iterations.
# Users may need to swap models if a specific id rejects `cached_content`.
MODEL_OPTIONS: dict[str, str] = {
    "Gemini 3.1 Flash-Lite":   "gemini-3.1-flash-lite",
    "Gemini 3.1 Flash":        "gemini-3.1-flash",
    "Gemini 3 Flash-Lite":     "gemini-3-flash-lite",
    "Gemini 2.5 Flash":        "gemini-2.5-flash",
    "Gemini 2.5 Flash-Lite":   "gemini-2.5-flash-lite",
}
DEFAULT_MODEL_LABEL = "Gemini 3.1 Flash-Lite"

# Name → definition lookup for the verification layer (false-positive audit
# needs each found row's metric definition, keyed by its `metric_target`).
_METRIC_BY_NAME: dict[str, MetricDef] = {m["name"]: m for m in METRIC_METADATA}


# Retry policy — mirrors POC1.run.
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


class NonRetryablePOC2Failure(SystemExit):
    """Raised on errors we won't keep retrying (auth, bad request, etc.).
    Aborts the whole run so the UI can show a clear actionable message."""


class PdfTooLargeError(Exception):
    """The PDF's token count exceeds the model's context window.

    We do NOT auto-split (a single annual report is ~100k–300k tokens and
    almost never approaches the ~1M window). When it DOES exceed, we skip
    that document with a clear message rather than silently truncating it.
    `run_extraction_company` catches this per-PDF and moves on to the next
    year instead of aborting the whole company.
    """


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


# ---------------------------------------------------------------------------
# Files API readiness gate
# ---------------------------------------------------------------------------

def _wait_for_active(sync_client, file_obj, *, timeout: float = 120.0,
                     interval: float = 1.5):
    """Poll the Files API until the uploaded file reaches ACTIVE state.

    Required before `caches.create()` — Gemini rejects cache creation against
    a file still in PROCESSING. The user's prototype skipped this poll and
    got away with it because the PDFs were small; we add it for robustness
    on larger annual reports (200+ pages can sit in PROCESSING for a few
    seconds).
    """
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
            raise RuntimeError(
                f"Files API reported state={state_str} for {file_obj.name}"
            )
        time.sleep(interval)
    raise TimeoutError(
        f"File {file_obj.name} did not reach ACTIVE within {timeout}s "
        f"(last state: {last_state})"
    )


# ---------------------------------------------------------------------------
# Token counting (FREE) + context-window guard
# ---------------------------------------------------------------------------

# Input context windows for the supported models. The Gemini 2.5 / 3 flash,
# flash-lite and pro lines all expose a ~1,048,576-token input window; we keep
# an explicit map so the guard is honest if a future model differs.
MODEL_CONTEXT_LIMITS: dict[str, int] = {
    "gemini-3.1-flash-lite": 1_048_576,
    "gemini-3.1-flash":      1_048_576,
    "gemini-3-flash-lite":   1_048_576,
    "gemini-2.5-flash":      1_048_576,
    "gemini-2.5-flash-lite": 1_048_576,
}
DEFAULT_CONTEXT_LIMIT = 1_048_576


def context_limit_for(model: str) -> int:
    """Input-token ceiling for `model` (falls back to the common 1M window)."""
    return MODEL_CONTEXT_LIMITS.get(model, DEFAULT_CONTEXT_LIMIT)


def count_tokens_for_file(sync_client, uploaded_file, *, model: str) -> int | None:
    """Token count of an uploaded file for `model`. FREE — `count_tokens` is
    not billed by the Gemini API.

    Returns the integer token count, or None if the API couldn't report it
    (we treat a counting hiccup as non-fatal — better to attempt extraction
    than to block a run over a failed pre-flight count).
    """
    try:
        resp = sync_client.models.count_tokens(
            model=model, contents=[uploaded_file],
        )
        return getattr(resp, "total_tokens", None)
    except Exception:  # noqa: BLE001
        return None


# ---------------------------------------------------------------------------
# Consolidated > Standalone document-level filter
# ---------------------------------------------------------------------------

def apply_consolidated_filter(rows: list[dict]) -> tuple[list[dict], dict]:
    """Document-level rule (user-defined):
       If ANY extracted row has entity_context == 'Consolidated', drop every
       row whose entity_context is not 'Consolidated'. Otherwise leave the
       set untouched.

    Rationale: when an Indian annual report publishes consolidated statements,
    standalone numbers describe just the parent entity (excluding subsidiaries)
    and the consolidated set is the company-level truth. Mixing both in the
    output muddles the entity scope.

    Returns (filtered_rows, stats_dict).
    """
    has_consolidated = any(
        (r.get("entity_context") or "").strip() == "Consolidated" for r in rows
    )
    if not has_consolidated:
        return list(rows), {
            "consolidated_present": False,
            "rows_in": len(rows),
            "rows_out": len(rows),
            "dropped_non_consolidated": 0,
        }
    kept = [r for r in rows
            if (r.get("entity_context") or "").strip() == "Consolidated"]
    return kept, {
        "consolidated_present": True,
        "rows_in": len(rows),
        "rows_out": len(kept),
        "dropped_non_consolidated": len(rows) - len(kept),
    }


@dataclass
class ExtractionResult:
    """In-memory result bundle returned to the UI."""
    company_display: str
    fy_year: str
    model: str
    extractions: list[dict] = field(default_factory=list)
    verified: list[dict] = field(default_factory=list)  # populated if verify=True
    coverage: dict[str, bool] = field(default_factory=dict)
    per_metric_log: list[dict] = field(default_factory=list)
    totals: dict[str, Any] = field(default_factory=dict)
    # Raw rows BEFORE the Consolidated > Standalone document-level filter.
    # Kept for transparency / audit — UI can show the dropped count.
    extractions_raw: list[dict] = field(default_factory=list)
    consolidated_filter_stats: dict[str, Any] = field(default_factory=dict)

    @property
    def found_count(self) -> int:
        return sum(1 for v in self.coverage.values() if v)

    @property
    def missing_count(self) -> int:
        return sum(1 for v in self.coverage.values() if not v)


# ---------------------------------------------------------------------------
# Parsing helpers
# ---------------------------------------------------------------------------

def _parse_response(response) -> tuple[list[dict], dict]:
    """Return (extracted_rows, usage). Raises _ResponseValidationError on bad output."""
    raw = getattr(response, "text", None) if response is not None else None
    if not raw:
        raise _ResponseValidationError("model returned an empty response body")
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as je:
        preview = raw[:300].replace("\n", " ")
        raise _ResponseValidationError(
            f"response was not valid JSON ({je}); preview: {preview!r}"
        ) from je
    if not isinstance(parsed, dict):
        raise _ResponseValidationError(
            f"response top-level is not an object: type={type(parsed).__name__}"
        )
    rows = parsed.get("extracted_metrics", [])
    if not isinstance(rows, list):
        raise _ResponseValidationError(
            f"`extracted_metrics` is not a list: type={type(rows).__name__}"
        )

    # Per-row Pydantic validation — drop bad rows, keep the rest. Same
    # philosophy as POC1: one fabricated row should not poison the whole
    # metric's result.
    kept: list[dict] = []
    dropped: list[dict] = []
    for row in rows:
        try:
            from POC2.models import ExtractedMetricPOC2
            validated = ExtractedMetricPOC2.model_validate(row)
        except ValidationError as ve:
            dropped.append({
                "row": row,
                "errors": [
                    {"loc": list(err.get("loc", ())),
                     "msg": err.get("msg", ""),
                     "type": err.get("type", "")}
                    for err in ve.errors()
                ],
            })
            continue
        kept.append(validated.model_dump())

    meta = getattr(response, "usage_metadata", None)
    usage = {
        "input_tokens": getattr(meta, "prompt_token_count", 0) or 0,
        "output_tokens": getattr(meta, "candidates_token_count", 0) or 0,
        "thinking_tokens": getattr(meta, "thinking_token_count", 0) or 0,
        "total_tokens": getattr(meta, "total_token_count", 0) or 0,
        "cached_tokens": getattr(meta, "cached_content_token_count", 0) or 0,
    }
    if dropped:
        usage["dropped_rows"] = dropped
    return kept, usage


def _parse_verification(response) -> dict:
    raw = getattr(response, "text", None) if response is not None else None
    if not raw:
        raise _ResponseValidationError("empty verification response")
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as je:
        raise _ResponseValidationError(f"verification not JSON: {je}") from je
    try:
        v = VerificationResponse.model_validate(parsed)
    except ValidationError as ve:
        raise _ResponseValidationError(f"verification schema mismatch: {ve}") from ve
    return v.model_dump()


# ---------------------------------------------------------------------------
# Per-metric extraction (one Gemini call, with retries)
# ---------------------------------------------------------------------------

async def _call_with_retry(
    *,
    label: str,
    client,
    model: str,
    contents: str,
    config: types.GenerateContentConfig,
    parse_fn: Callable[[Any], Any],
    emit: Callable[[str], None],
) -> tuple[Any, dict, int]:
    """Single Gemini call wrapped in the infinite-retry policy.

    Returns (parsed, usage, attempts).
    Raises NonRetryablePOC2Failure on permanent failure.
    """
    attempt = 0
    while True:
        attempt += 1
        t0 = time.time()
        try:
            response = await client.models.generate_content(
                model=model, contents=contents, config=config,
            )
            parsed = parse_fn(response)
            if isinstance(parsed, tuple):
                rows, usage = parsed
            else:
                # Verification: parse_fn returns a single dict; no usage info.
                rows = parsed
                meta = getattr(response, "usage_metadata", None)
                usage = {
                    "input_tokens": getattr(meta, "prompt_token_count", 0) or 0,
                    "output_tokens": getattr(meta, "candidates_token_count", 0) or 0,
                    "total_tokens": getattr(meta, "total_token_count", 0) or 0,
                    "cached_tokens": getattr(meta, "cached_content_token_count", 0) or 0,
                }
            return rows, usage, attempt
        except Exception as e:  # noqa: BLE001
            elapsed = time.time() - t0
            err_type = type(e).__name__
            err_msg = (str(e) or repr(e))[:300]
            if not _is_retryable(e):
                tb = traceback.format_exc(limit=3)
                msg = (f"[{label}] non-retryable {err_type}: {err_msg}\n"
                       f"{tb}")
                emit(msg)
                raise NonRetryablePOC2Failure(msg) from e
            wait = _backoff_seconds(attempt)
            emit(f"[{label}] attempt {attempt} failed in {elapsed:.1f}s "
                 f"({err_type}: {err_msg[:160]}); retry in {wait:.1f}s")
            await asyncio.sleep(wait)


async def _extract_one_metric(
    *,
    metric: MetricDef,
    client,
    model: str,
    cache_name: str,
    semaphore: asyncio.Semaphore,
    emit: Callable[[str], None],
) -> dict:
    """Issue one cached-content call for one metric. Returns a per-metric log."""
    label = f"M[{metric['name'][:24]}]"
    prompt = build_metric_prompt(metric)
    config = types.GenerateContentConfig(
        cached_content=cache_name,
        response_mime_type="application/json",
        response_schema=Prompt2Response.model_json_schema(),
        temperature=0.0,
        top_k=1,
        seed=42,
    )

    async with semaphore:
        t0 = time.time()
        emit(f"[{label}] starting (model={model})")
        try:
            rows, usage, attempts = await _call_with_retry(
                label=label, client=client, model=model,
                contents=prompt, config=config, parse_fn=_parse_response,
                emit=emit,
            )
        except NonRetryablePOC2Failure:
            return {
                "metric": metric["name"], "status": "error",
                "elapsed_s": round(time.time() - t0, 2),
                "rows": [], "usage": {}, "attempts": -1,
            }

    # Drop null-valued rows here — they signal "metric not present", which
    # POC2's NULL MANDATE allows but the UI doesn't want to display as a hit.
    non_null = [r for r in rows if r.get("current_year_value") is not None]
    elapsed = time.time() - t0
    drop_note = ""
    if len(rows) != len(non_null):
        drop_note = f" (dropped {len(rows) - len(non_null)} null rows)"
    emit(f"[{label}] OK — {len(non_null)} disclosure(s){drop_note} in "
         f"{elapsed:.1f}s | in={usage.get('input_tokens', 0)} "
         f"out={usage.get('output_tokens', 0)} "
         f"cached={usage.get('cached_tokens', 0)} "
         f"| attempts={attempts}")
    return {
        "metric": metric["name"], "status": "ok",
        "elapsed_s": round(elapsed, 2),
        "rows": non_null,
        "usage": usage,
        "attempts": attempts,
        "raw_row_count": len(rows),
        "kept_row_count": len(non_null),
    }


# ---------------------------------------------------------------------------
# Verification layer
# ---------------------------------------------------------------------------

async def _verify_one(
    *,
    item: dict,
    metric: MetricDef,
    client,
    model: str,
    cache_name: str,
    semaphore: asyncio.Semaphore,
    emit: Callable[[str], None],
) -> dict:
    label = f"V[{item.get('metric_target', '?')[:24]}]"
    prompt = build_verification_prompt(item, metric)
    config = types.GenerateContentConfig(
        cached_content=cache_name,
        response_mime_type="application/json",
        response_schema=VerificationResponse.model_json_schema(),
        temperature=0.0,
        top_k=1,
        seed=42,
    )
    async with semaphore:
        t0 = time.time()
        try:
            parsed, usage, _ = await _call_with_retry(
                label=label, client=client, model=model,
                contents=prompt, config=config, parse_fn=_parse_verification,
                emit=emit,
            )
        except NonRetryablePOC2Failure:
            emit(f"[{label}] non-retryable failure during verification")
            return {**item, "verified": False,
                    "verification_note": "non-retryable error", "verification_usage": {}}
    elapsed = time.time() - t0
    emit(f"[{label}] {'VERIFIED' if parsed.get('verified') else 'CORRECTION'} "
         f"in {elapsed:.1f}s — {parsed.get('reason', '')[:120]}")
    return {
        **item,
        "verified": bool(parsed.get("verified")),
        "verification_note": parsed.get("reason", ""),
        "verification_usage": usage,
    }


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

async def run_extraction(
    doc: DocPaths2,
    *,
    model: str = DEFAULT_MODEL,
    do_verify: bool = False,
    concurrency: int = 4,
    cache_ttl_seconds: int = 7200,
    max_input_tokens: int | None = None,
    progress_callback: Callable[[str], None] | None = None,
) -> ExtractionResult:
    """End-to-end POC2 pipeline. See module docstring for lifecycle.

    `progress_callback`, if supplied, receives each pipeline event as a single
    string. The Streamlit UI uses this to drive `st.status.write(...)` directly,
    so we no longer need to tee stdout from a worker thread. When omitted
    (e.g. CLI runs), events fall back to plain print().
    """
    emit: Callable[[str], None] = progress_callback or print

    async_client = make_async_client()
    # We use the sync client for cache + file lifecycle ops only — the async
    # client has the same surface but sync caches.create() is simpler to
    # reason about and we only invoke it twice (create + delete) per run.
    sync_client = make_sync_client()

    system_instruction = build_system_instruction(doc.company_display, doc.fy_year)

    uploaded_file = None
    cache = None
    t_total = time.time()

    emit("=" * 70)
    emit(f"POC2 — {model}")
    emit(f"PDF:        {doc.pdf_path}")
    emit(f"Company:    {doc.company_display}   |   FY: {doc.fy_year}")
    emit(f"Metrics:    {len(METRIC_METADATA)}  |  Concurrency: {concurrency}  |  "
         f"Verify: {do_verify}")
    emit("=" * 70)

    try:
        # ── 1. Upload PDF ────────────────────────────────────────────────
        t_up = time.time()
        emit(f"[upload] sending {doc.pdf_path.name} to Gemini Files API…")
        uploaded_file = sync_client.files.upload(file=str(doc.pdf_path))
        emit(f"[upload] done in {time.time() - t_up:.1f}s — {uploaded_file.name}")

        # Wait until the file is ACTIVE — caches.create() rejects PROCESSING
        # files. Cheap when the file is already ACTIVE on first poll.
        t_active = time.time()
        uploaded_file = _wait_for_active(sync_client, uploaded_file)
        emit(f"[upload] file ACTIVE in {time.time() - t_active:.1f}s")

        # ── 1b. Pre-flight token count (FREE) + context-window guard ─────
        # count_tokens is NOT billed. We report the PDF's size so cost is
        # predictable, and refuse to proceed if it exceeds the model's input
        # window (we skip rather than auto-split — see PdfTooLargeError).
        limit = max_input_tokens if max_input_tokens is not None \
            else context_limit_for(model)
        n_tokens = count_tokens_for_file(sync_client, uploaded_file, model=model)
        if n_tokens is None:
            emit("[tokens] count unavailable — proceeding without guard")
        else:
            emit(f"[tokens] PDF ≈ {n_tokens:,} tokens  (limit {limit:,}, "
                 f"{100 * n_tokens / limit:.0f}% of window)")
            if n_tokens > limit:
                raise PdfTooLargeError(
                    f"PDF is ~{n_tokens:,} tokens, over the {limit:,}-token "
                    f"window for {model}. Skipped (no auto-split)."
                )

        # ── 2. Create cache (system instruction + uploaded PDF) ──────────
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

        # ── 3. Per-metric extraction (concurrent, bounded) ───────────────
        semaphore = asyncio.Semaphore(concurrency)
        per_metric_tasks: list[Awaitable[dict]] = [
            _extract_one_metric(
                metric=m, client=async_client, model=model,
                cache_name=cache.name, semaphore=semaphore, emit=emit,
            )
            for m in METRIC_METADATA
        ]
        per_metric_results = await asyncio.gather(*per_metric_tasks)

        # Flatten extractions — coverage is computed AFTER the consolidated
        # filter so the "found/missing" table reflects what actually ships.
        raw_rows: list[dict] = []
        for log in per_metric_results:
            if log["status"] == "ok" and log["rows"]:
                raw_rows.extend(log["rows"])

        # ── 4. Consolidated > Standalone document-level filter ──────────
        # If any single metric was tagged Consolidated, drop everything else.
        # This collapses the entity scope to the company-level (parent +
        # subsidiaries) view. See apply_consolidated_filter() for rationale.
        all_rows, cf_stats = apply_consolidated_filter(raw_rows)
        if cf_stats["consolidated_present"]:
            emit(f"[filter] Consolidated present — dropped "
                 f"{cf_stats['dropped_non_consolidated']} non-Consolidated "
                 f"row(s) (kept {cf_stats['rows_out']}/{cf_stats['rows_in']}).")
        else:
            emit(f"[filter] No Consolidated rows — keeping all "
                 f"{cf_stats['rows_out']} extracted row(s) as-is.")

        # Coverage map reflects post-filter survivors.
        surviving_targets = {(r.get("metric_target") or "").strip()
                             for r in all_rows}
        coverage: dict[str, bool] = {
            m["name"]: (m["name"] in surviving_targets) for m in METRIC_METADATA
        }

        # ── 5. Optional verification ─────────────────────────────────────
        verified_rows: list[dict] = []
        if do_verify and all_rows:
            emit(f"[verify] auditing {len(all_rows)} extraction(s) …")
            v_sem = asyncio.Semaphore(concurrency)
            verify_tasks = [
                _verify_one(
                    item=r,
                    metric=_METRIC_BY_NAME.get(
                        (r.get("metric_target") or "").strip(),
                        {"name": r.get("metric_target", ""),
                         "definition": "(definition unavailable)"},
                    ),
                    client=async_client, model=model,
                    cache_name=cache.name, semaphore=v_sem, emit=emit,
                )
                for r in all_rows
            ]
            verified_rows = await asyncio.gather(*verify_tasks)

        # ── 6. Totals + return ───────────────────────────────────────────
        total_in = sum(l["usage"].get("input_tokens", 0)
                       for l in per_metric_results if l.get("usage"))
        total_out = sum(l["usage"].get("output_tokens", 0)
                        for l in per_metric_results if l.get("usage"))
        total_cached = sum(l["usage"].get("cached_tokens", 0)
                           for l in per_metric_results if l.get("usage"))
        v_in = sum(r.get("verification_usage", {}).get("input_tokens", 0)
                   for r in verified_rows)
        v_out = sum(r.get("verification_usage", {}).get("output_tokens", 0)
                    for r in verified_rows)

        totals = {
            "metrics_total": len(METRIC_METADATA),
            "metrics_found": sum(1 for v in coverage.values() if v),
            "extractions_raw": len(raw_rows),
            "extractions_total": len(all_rows),
            "consolidated_filter": cf_stats,
            "tokens_in_extraction": total_in,
            "tokens_out_extraction": total_out,
            "tokens_cached_hits": total_cached,
            "tokens_in_verification": v_in,
            "tokens_out_verification": v_out,
            "elapsed_seconds": round(time.time() - t_total, 2),
        }

        emit("=" * 70)
        emit("POC2 DONE")
        emit(f"  Metrics found:   {totals['metrics_found']}/{totals['metrics_total']}")
        emit(f"  Extractions:     {totals['extractions_total']}")
        emit(f"  Tokens (extr):   in={total_in:,} out={total_out:,} "
             f"cached={total_cached:,}")
        if do_verify:
            emit(f"  Tokens (verify): in={v_in:,} out={v_out:,}")
        emit(f"  Elapsed:         {totals['elapsed_seconds']}s")
        emit("=" * 70)

        return ExtractionResult(
            company_display=doc.company_display,
            fy_year=doc.fy_year,
            model=model,
            extractions=all_rows,
            verified=verified_rows,
            coverage=coverage,
            per_metric_log=per_metric_results,
            totals=totals,
            extractions_raw=raw_rows,
            consolidated_filter_stats=cf_stats,
        )

    finally:
        # Best-effort cleanup. POC2 ethos: nothing persists between runs.
        if cache is not None:
            try:
                sync_client.caches.delete(name=cache.name)
                emit(f"[cleanup] cache deleted: {cache.name}")
            except Exception as e:  # noqa: BLE001
                emit(f"[cleanup] cache delete failed: {e!r}")
        if uploaded_file is not None:
            try:
                sync_client.files.delete(name=uploaded_file.name)
                emit(f"[cleanup] uploaded file deleted: {uploaded_file.name}")
            except Exception as e:  # noqa: BLE001
                emit(f"[cleanup] file delete failed: {e!r}")


# ---------------------------------------------------------------------------
# Company-level driver
# ---------------------------------------------------------------------------

async def run_extraction_company(
    company_dir: Path | str,
    *,
    model: str = DEFAULT_MODEL,
    do_verify: bool = False,
    concurrency: int = 4,
    cache_ttl_seconds: int = 7200,
    max_input_tokens: int | None = None,
    progress_callback: Callable[[str], None] | None = None,
) -> dict:
    """Run the per-document pipeline over every PDF in one company folder.

    Layout (folder name = company, each PDF filename = its FY year):
        <company_dir>/
            2021.pdf   2022.pdf   2023.pdf

    For each PDF we derive a DocPaths2 (company ← folder name, year ← filename),
    run `run_extraction`, and write a per-year workbook NEXT TO the PDF
    (e.g. 2023.pdf → 2023.xlsx). PDFs are processed SEQUENTIALLY — each
    `run_extraction` is already internally concurrent across its 37 metrics, so
    serial documents keep one cache + one upload alive at a time and make cost
    predictable. A failure on one year (including PdfTooLargeError) is logged
    and skipped; the remaining years still run.

    Returns a summary dict: company, per-PDF outcomes, and roll-up totals.
    """
    emit: Callable[[str], None] = progress_callback or print

    # openpyxl is a heavy import — keep it lazy, matching excel_export's intent.
    from POC2.excel_export import build_excel_workbook

    company_dir = Path(company_dir)
    if not company_dir.is_dir():
        raise NotADirectoryError(f"Not a directory: {company_dir}")

    company_name = company_dir.name
    pdfs = sorted(company_dir.glob("*.pdf"))

    emit("#" * 70)
    emit(f"COMPANY: {company_name}  ({len(pdfs)} PDF(s))  |  dir={company_dir}")
    emit("#" * 70)

    if not pdfs:
        emit(f"[company] no PDFs found in {company_dir}")
        return {"company": company_name, "company_dir": str(company_dir),
                "pdfs": [], "succeeded": 0, "failed": 0, "totals": {}}

    outcomes: list[dict] = []
    t_company = time.time()

    for pdf in pdfs:
        doc = derive_paths(pdf, company_name=company_name)
        emit(f"\n[company] ── {pdf.name}  →  FY {doc.fy_year} ──")
        try:
            result = await run_extraction(
                doc, model=model, do_verify=do_verify, concurrency=concurrency,
                cache_ttl_seconds=cache_ttl_seconds,
                max_input_tokens=max_input_tokens, progress_callback=emit,
            )
            xlsx_path = pdf.with_suffix(".xlsx")
            xlsx_path.write_bytes(build_excel_workbook(result))
            emit(f"[company] saved → {xlsx_path}")
            outcomes.append({
                "pdf": pdf.name,
                "fy_year": doc.fy_year,
                "status": "ok",
                "xlsx_path": str(xlsx_path),
                "metrics_found": result.totals.get("metrics_found"),
                "extractions": result.totals.get("extractions_total"),
                "totals": result.totals,
            })
        except PdfTooLargeError as e:
            emit(f"[company] SKIPPED {pdf.name}: {e}")
            outcomes.append({"pdf": pdf.name, "fy_year": doc.fy_year,
                             "status": "skipped_too_large", "error": str(e)})
        except Exception as e:  # noqa: BLE001
            emit(f"[company] FAILED {pdf.name}: {type(e).__name__}: {e}")
            outcomes.append({"pdf": pdf.name, "fy_year": doc.fy_year,
                             "status": "error", "error": f"{type(e).__name__}: {e}"})

    ok = [o for o in outcomes if o["status"] == "ok"]
    roll_up = {
        "tokens_in_extraction": sum(o.get("totals", {}).get("tokens_in_extraction", 0) for o in ok),
        "tokens_out_extraction": sum(o.get("totals", {}).get("tokens_out_extraction", 0) for o in ok),
        "tokens_cached_hits": sum(o.get("totals", {}).get("tokens_cached_hits", 0) for o in ok),
    }

    emit("#" * 70)
    emit(f"COMPANY DONE: {company_name}  |  ok={len(ok)}  "
         f"failed={len(outcomes) - len(ok)}  |  {time.time() - t_company:.1f}s")
    emit("#" * 70)

    return {
        "company": company_name,
        "company_dir": str(company_dir),
        "pdfs": outcomes,
        "succeeded": len(ok),
        "failed": len(outcomes) - len(ok),
        "totals": roll_up,
    }






# funtion to pdfs_directory
# extract the information of each company available in and pdfs along with the path => arr[comp] -> if done store the execel path
# for comp in arr[comp]: run_extraction_comapny() -> once done, merge all the excel in the mega sheet

# PLAN :
# 1. run one comapny, to ensure the costing before going for the first scale, caching workings
# Average time to process any video, length of the pdf, 
# 2. Calculate the token cosumption and caching burn, mechanism to increse the existing cache timing or not, if yes, then track the timing during the process.
# 3. if the cost < 5k, then we are good to do the scale. 

# run the scale


# ---------------------------------------------------------------------------
# CLI runner — single company (Phase 1 of the PLAN above)
# ---------------------------------------------------------------------------
# Filenames like 13.pdf / 14.pdf need NO renaming: derive_year_from_filename
# already maps "13" → FY13 / March 31, 2013. Just point at the company folder.

# if __name__ == "__main__":
#     COMPANY_DIR = "pdfs/3M India Ltd"

#     summary = asyncio.run(
#         run_extraction_company(
#             COMPANY_DIR,
#             model=DEFAULT_MODEL,
#             do_verify=True,
#             concurrency=5,
#             cache_ttl_seconds=7200,
#         )
#     )

#     print("\n" + "=" * 70)
#     print(f"SUMMARY — {summary['company']}: "
#           f"{summary['succeeded']} ok / {summary['failed']} failed")
#     for o in summary["pdfs"]:
#         line = f"  {o['pdf']:<10} {o['status']:<18} {o.get('fy_year', '')}"
#         if o["status"] == "ok":
#             line += f"  found={o['metrics_found']}  rows={o['extractions']}  → {o['xlsx_path']}"
#         else:
#             line += f"  {o.get('error', '')}"
#         print(line)
#     print("=" * 70)


