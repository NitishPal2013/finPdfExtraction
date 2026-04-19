"""
Simple SDK call: gemini-3.1-flash-lite-preview, 75 pages per window.

No retries, no split fallback, no parallelism. Just the plain Gemini SDK:
upload images → generate_content → save JSON. One file per window.

Usage:
  python -m POC1.run <pdf_path> [--company-name X] [--fy-year Y]

Examples:
  python -m POC1.run pdfs/jyotilabs/23.pdf
  python -m POC1.run pdfs/hdfcbank/24.pdf --company-name "HDFC Bank"

Convention (see POC1/paths.py for full details):
  Input    pdfs/<company>/<year>.pdf
  Cache    pdfs/<company>/<year>_pages/page_N.png   (auto-rasterized)
  Output   POC1/results/<company>_<year>/
"""
from __future__ import annotations

import argparse
import asyncio
import json
import random
import time
import traceback
from pathlib import Path

import httpx
from google.genai import errors as gerrors
from google.genai import types

from .file_utils import delete_files, upload_files
from .gemini_client import make_async_client
from .models import Prompt15Response
from .paths import DocPaths, add_common_args, derive_paths, ensure_images
from .prompt import prompt_template

MODEL = "gemini-3.1-flash-lite-preview"
WINDOW_SIZE = 75
OVERLAP = 10
STEP = WINDOW_SIZE - OVERLAP  # 65

# Retry policy: infinite retries on transient errors. Backoff grows
# exponentially (BASE_DELAY * 2^(n-1)) capped at MAX_DELAY, plus ±20% jitter.
# Non-retryable errors abort the run immediately so we don't burn money on
# a permanently broken request (e.g. auth, model-not-found, code bug).
BASE_DELAY = 2.0
MAX_DELAY = 60.0

# Errors we retry on: transient server / network / parse failures. Anything
# else (auth, malformed request, code bugs) propagates immediately.
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


def _is_retryable(exc: BaseException) -> bool:
    """Return True if `exc` is worth a backoff + retry."""
    if isinstance(exc, _ResponseValidationError):
        return True  # truncated/garbled output — give the model another shot
    if isinstance(exc, RETRYABLE_NETWORK_ERRORS):
        return True
    if isinstance(exc, gerrors.ClientError):
        # 429 (rate limit) is the only retryable 4xx; the rest are our bugs.
        status = getattr(exc, "code", None) or getattr(exc, "status_code", None)
        return status == 429
    return False


def _backoff_seconds(attempt: int) -> float:
    """Exponential backoff with ±20% jitter."""
    base = min(MAX_DELAY, BASE_DELAY * (2 ** (attempt - 1)))
    return base * (0.8 + 0.4 * random.random())


def build_windows(total: int, size: int, step: int) -> list[tuple[int, int]]:
    windows: list[tuple[int, int]] = []
    start = 1
    while start <= total:
        end = min(start + size - 1, total)
        windows.append((start, end))
        if end == total:
            break
        start += step
    return windows


def _build_request(
    start: int,
    end: int,
    uploaded_map: dict,
    image_dir: Path,
    system_instruction: str,
) -> tuple[list, types.GenerateContentConfig]:
    """Assemble the (parts, config) tuple — built once per window, reused on retries."""
    parts = []
    for page in range(start, end + 1):
        uf = uploaded_map[str(image_dir / f"page_{page}.png")]
        parts.append(types.Part.from_uri(file_uri=uf.uri, mime_type=uf.mime_type))
    parts.append(types.Part.from_text(
        text=(
            f"This chunk covers document pages {start} through {end} "
            f"(inclusive). Use these absolute page numbers in the `page_number` field."
        )
    ))
    config = types.GenerateContentConfig(
        system_instruction=system_instruction,
        temperature=0.0,
        top_k=1,
        seed=42,
        response_schema=Prompt15Response.model_json_schema(),
        response_mime_type="application/json",
        # Caching note: we deliberately do NOT set `cached_content`. This pipeline
        # processes each PDF once and discards the upload — explicit caches would
        # only add cost. (Implicit prefix caching on Gemini 2.5/3.x is server-side
        # and *reduces* input-token cost; nothing we can or should disable.)
    )
    return parts, config


def _parse_and_validate(response) -> tuple[dict, dict]:
    """Parse the model response into (parsed_json, usage). Raises on bad output."""
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
    if not isinstance(parsed, dict) or not isinstance(parsed.get("extracted_metrics"), list):
        raise _ResponseValidationError(
            f"response missing/invalid `extracted_metrics`; "
            f"got top-level type={type(parsed).__name__}, "
            f"keys={list(parsed.keys()) if isinstance(parsed, dict) else 'n/a'}"
        )
    meta = getattr(response, "usage_metadata", None)
    usage = {
        "input_tokens": getattr(meta, "prompt_token_count", 0) or 0,
        "output_tokens": getattr(meta, "candidates_token_count", 0) or 0,
        "thinking_tokens": getattr(meta, "thinking_token_count", 0) or 0,
        "total_tokens": getattr(meta, "total_token_count", 0) or 0,
    }
    return parsed, usage


class NonRetryableWindowFailure(SystemExit):
    """Raised when a window fails with an error we won't keep retrying.
    Aborts the whole run so we don't burn money / produce a partial merge."""


async def call_window(
    idx: int,
    start: int,
    end: int,
    uploaded_map: dict,
    image_dir: Path,
    output_dir: Path,
    system_instruction: str,
    *,
    client,
) -> dict:
    """Call Gemini for one window. Retries forever on transient errors;
    aborts the whole run on non-retryable errors. Always writes a JSON record.

    `client` MUST be a fresh client bound to the currently running event loop
    (use `make_async_client()` at the top of your async entry point)."""
    label = f"W{idx}"
    n = end - start + 1
    out_path = output_dir / f"window_{idx:02d}_pages_{start}-{end}.json"
    parts, config = _build_request(start, end, uploaded_map, image_dir, system_instruction)

    attempts: list[dict] = []
    overall_t0 = time.time()
    attempt = 0

    while True:
        attempt += 1
        attempt_t0 = time.time()
        try:
            print(f"[{label}] attempt {attempt} — pages {start}-{end} ({n} imgs)")
            response = await client.models.generate_content(
                model=MODEL,
                contents=parts,
                config=config,
            )
            parsed, usage = _parse_and_validate(response)
        except Exception as e:  # noqa: BLE001
            elapsed = time.time() - attempt_t0
            err_type = type(e).__name__
            err_msg = str(e) or repr(e)
            attempts.append({
                "attempt": attempt,
                "error_type": err_type,
                "error_msg": err_msg[:500],
                "traceback": traceback.format_exc(limit=3),
                "elapsed_s": round(elapsed, 2),
            })

            if not _is_retryable(e):
                total_elapsed = time.time() - overall_t0
                rec = {
                    "window_index": idx,
                    "start_page": start, "end_page": end,
                    "num_images": n, "model": MODEL,
                    "status": "error",
                    "error": err_msg[:500],
                    "error_type": err_type,
                    "retryable": False,
                    "total_attempts": attempt,
                    "elapsed_s": round(total_elapsed, 2),
                    "attempt_log": attempts,
                }
                with open(out_path, "w", encoding="utf-8") as f:
                    json.dump(rec, f, indent=2, default=str)
                msg = (
                    f"[{label}] ABORTED on non-retryable error after {attempt} "
                    f"attempts in {total_elapsed:.1f}s: {err_type}: {err_msg[:200]}\n"
                    f"  Inspect {out_path.name} for full traceback. Re-run after fixing."
                )
                print(msg)
                # Halt the entire pipeline — we can't merge without all windows.
                raise NonRetryableWindowFailure(msg) from e

            wait = _backoff_seconds(attempt)
            print(f"[{label}] attempt {attempt} failed in {elapsed:.1f}s "
                  f"({err_type}: {err_msg[:160]}); retry in {wait:.1f}s")
            await asyncio.sleep(wait)
            continue

        # SUCCESS
        elapsed = time.time() - attempt_t0
        total_elapsed = time.time() - overall_t0
        attempts.append({
            "attempt": attempt, "status": "ok", "elapsed_s": round(elapsed, 2),
        })
        num = len(parsed["extracted_metrics"])
        rec = {
            "window_index": idx,
            "start_page": start, "end_page": end,
            "num_images": n, "model": MODEL,
            "status": "ok",
            "total_attempts": attempt,
            "elapsed_s": round(total_elapsed, 2),
            "gen_elapsed_s": round(elapsed, 2),
            "usage": usage,
            "num_extractions": num,
            "attempt_log": attempts,
            "response": parsed,
        }
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(rec, f, indent=2, ensure_ascii=False, default=str)
        retry_note = f" (after {attempt - 1} retries)" if attempt > 1 else ""
        print(f"[{label}] OK — {num} metrics in {elapsed:.1f}s{retry_note} | "
              f"in={usage['input_tokens']} out={usage['output_tokens']} → {out_path.name}")
        return rec


def _load_completed_window(path: Path) -> dict | None:
    """Return the existing record if this window already completed successfully,
    else None. Used by `run()` to skip already-done work on resume."""
    if not path.exists():
        return None
    try:
        rec = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    if rec.get("status") == "ok" and isinstance(rec.get("response"), dict):
        return rec
    return None


async def run(doc: DocPaths) -> None:
    image_dir, total_pages = ensure_images(doc.pdf_path, doc.image_dir)
    doc.output_dir.mkdir(parents=True, exist_ok=True)
    windows = build_windows(total_pages, WINDOW_SIZE, STEP)

    system_instruction = (
        prompt_template
        .replace("[INSERT_COMPANY_NAME]", doc.company_display)
        .replace("[INSERT_TARGET_FY_YEAR]", doc.fy_year)
    )

    # ── Resume: pick up where a previous run left off ─────────────────────────
    # A window is considered "done" if its per-window JSON exists and has
    # status=ok with a parsed response. Anything else (missing, error, partial)
    # is re-attempted from scratch.
    completed: dict[int, dict] = {}
    pending: list[tuple[int, int, int]] = []
    for i, (s, e) in enumerate(windows, start=1):
        rec = _load_completed_window(doc.output_dir / f"window_{i:02d}_pages_{s}-{e}.json")
        if rec is not None:
            completed[i] = rec
        else:
            pending.append((i, s, e))

    print("=" * 70)
    print(f"SIMPLE — {MODEL}")
    print(f"PDF:        {doc.pdf_path}")
    print(f"Company:    {doc.company_display}   |   FY:  {doc.fy_year}")
    print(f"Images:     {image_dir}  ({total_pages} pages)")
    print(f"Output:     {doc.output_dir}")
    print(f"Windows ({len(windows)}): {windows}")
    if completed:
        print(f"[resume] {len(completed)}/{len(windows)} window(s) already complete — will skip:")
        for i in sorted(completed):
            r = completed[i]
            print(f"  ✓ W{i} pages {r['start_page']}-{r['end_page']} "
                  f"({r.get('num_extractions', 0)} metrics)")
    print(f"[plan]   {len(pending)} window(s) to process")
    print("=" * 70)

    t_total = time.time()
    processed: dict[int, dict] = {}
    uploaded: list = []

    # Build a fresh Gemini client bound to the currently running event loop.
    # MUST be created here (not at module scope) — Streamlit triggers a new
    # asyncio.run per click, and stale loop-bound clients crash on reuse.
    client = make_async_client()

    if pending:
        # Upload only the pages needed by pending windows — saves time + tokens
        # on a partial resume.
        pages = set()
        for _, s, e in pending:
            pages.update(range(s, e + 1))
        image_paths = [str(image_dir / f"page_{p}.png") for p in sorted(pages)]
        print(f"[upload] {len(image_paths)} unique images for {len(pending)} pending window(s)...")
        t_up = time.time()
        uploaded = await upload_files(image_paths, client=client)
        print(f"[upload] done in {time.time() - t_up:.1f}s")
        uploaded_map = {image_paths[i]: uploaded[i] for i in range(len(image_paths))}

        try:
            for i, s, e in pending:
                processed[i] = await call_window(
                    i, s, e, uploaded_map, image_dir, doc.output_dir,
                    system_instruction, client=client,
                )
        finally:
            # Delete uploads only on full success of all pending windows.
            # If we aborted (or were Ctrl-C'd), keep the files alive so a resume
            # within 48h can re-use them. Files API auto-expires after that.
            if uploaded and len(processed) == len(pending):
                try:
                    await delete_files(uploaded, client=client)
                except Exception as ex:  # noqa: BLE001
                    print(f"[cleanup] warning: {ex!r}")
            elif uploaded:
                print(f"[cleanup] keeping {len(uploaded)} uploaded files alive "
                      f"(Files API auto-expires in 48h) — useful if you resume.")

    total_elapsed = time.time() - t_total

    # Combine completed + processed in original window order.
    results: list[dict] = []
    for i, (s, e) in enumerate(windows, start=1):
        results.append(completed.get(i) or processed[i])

    total_in = sum(r.get("usage", {}).get("input_tokens", 0) for r in results)
    total_out = sum(r.get("usage", {}).get("output_tokens", 0) for r in results)
    total_extr = sum(r.get("num_extractions", 0) for r in results)
    n_fail = sum(1 for r in results if r.get("status") == "error")

    total_attempts = sum(r.get("total_attempts", 1) for r in results)
    summary = {
        "model": MODEL,
        "pdf_path": str(doc.pdf_path),
        "company": doc.company_display,
        "fy_year": doc.fy_year,
        "total_pages": total_pages,
        "window_size": WINDOW_SIZE, "overlap": OVERLAP, "step": STEP,
        "num_windows": len(windows),
        "total_elapsed_s": round(total_elapsed, 2),
        "retry_policy": {
            "max_attempts": "unlimited (until success or non-retryable error)",
            "base_delay_s": BASE_DELAY,
            "max_delay_s": MAX_DELAY,
        },
        "resume": {
            "windows_skipped": len(completed),
            "windows_processed_this_run": len(processed),
        },
        "totals": {
            "input_tokens": total_in,
            "output_tokens": total_out,
            "num_extractions": total_extr,
            "num_failures": n_fail,
            "num_attempts_across_all_windows": total_attempts,
            "num_retries": total_attempts - len(windows),
        },
        "per_window": [
            {
                "window_index": r["window_index"],
                "start_page": r["start_page"], "end_page": r["end_page"],
                "status": r.get("status"),
                "num_extractions": r.get("num_extractions", 0),
                "total_attempts": r.get("total_attempts", 1),
                "elapsed_s": r.get("elapsed_s"),
                "gen_elapsed_s": r.get("gen_elapsed_s"),
                "input_tokens": r.get("usage", {}).get("input_tokens", 0),
                "output_tokens": r.get("usage", {}).get("output_tokens", 0),
                "error": r.get("error"),
                "error_type": r.get("error_type"),
                "attempt_log": r.get("attempt_log", []),
            }
            for r in results
        ],
    }
    with open(doc.summary_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False, default=str)

    print("\n" + "=" * 70)
    print("DONE")
    print("=" * 70)
    print(f"  Windows:      {len(windows)}  (failures: {n_fail})")
    print(f"  Total attempts:{total_attempts}  (retries: {total_attempts - len(windows)})")
    print(f"  Extractions:  {total_extr}")
    print(f"  Elapsed:      {total_elapsed:.1f}s")
    print(f"  Tokens in/out:{total_in:,} / {total_out:,}")
    print(f"  Summary:      {doc.summary_path}")
    print(f"  Per-window:   {doc.output_dir}")
    if n_fail > 0:
        # With infinite retries, an `error` status only happens for non-retryable
        # failures that aborted the run. Should never reach here under normal flow.
        print(f"\n  ⚠ {n_fail} window(s) ended in error state.")
        print(f"     See `attempt_log` in each window JSON for the full traceback.")
    print(f"\nNext: python -m POC1.merge {doc.pdf_path}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run the simple Gemini extraction pipeline on a PDF."
    )
    add_common_args(parser)
    args = parser.parse_args()
    doc = derive_paths(
        args.pdf_path,
        company_override=args.company_name,
        fy_override=args.fy_year,
    )
    asyncio.run(run(doc))


if __name__ == "__main__":
    main()
