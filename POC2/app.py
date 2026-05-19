"""
Streamlit UI for the POC2 financial metric extractor.

Differences from POC1:
  - No PDF rasterization (no `lit` CLI, no images on disk).
  - No persistent results / images / per-window JSON. Everything lives in
    memory for the duration of the session. The PDF itself is a tempfile
    that we unlink as soon as the pipeline returns.
  - Single-document workflow per click. No storage-management sidebar.
  - Live progress + final results pane + JSON / log downloads.

Run:
  streamlit run POC2/app.py


Streamlit rerun model — why we use `st.session_state`
-----------------------------------------------------
Streamlit re-executes the whole script on every interaction (download button
click, sidebar widget change, etc.), and `st.button()` only returns True on
the SCRIPT RUN where the click happened. If we re-derived `result` only when
`submit` is True, the user clicking any download button (or wiggling the
sidebar) would rerun the script with `submit=False` and lose the entire
results page. So we cache the result in `st.session_state` and render the
view from there on every run. The extraction itself runs only when the user
explicitly clicks "Run extraction" again.
"""
from __future__ import annotations

import asyncio
import json as _json
import queue as _queue
import re
import sys
import threading as _threading
import time as _time
from pathlib import Path

# `streamlit run POC2/app.py` puts POC2/ on sys.path, not the project root —
# so `import POC2.*` would fail. Add the project root before any POC2 imports.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import streamlit as st  # noqa: E402

from POC2.extractor import (  # noqa: E402
    DEFAULT_MODEL_LABEL,
    MODEL_OPTIONS,
    NonRetryablePOC2Failure,
    run_extraction,
)
from POC2.paths import (  # noqa: E402
    derive_paths,
    derive_year_from_filename,
    temp_pdf,
)


# ---------------------------------------------------------------------------
# Live log tailing — same idiom as POC1.app:
# the pipeline emits per-call progress via plain `print()`. We run it on a
# worker thread, tee stdout/stderr into a queue, and let the Streamlit main
# thread drain that queue so the UI updates while the work runs.
# ---------------------------------------------------------------------------

class _LineTee:
    def __init__(self, original, q: "_queue.Queue[str | None]") -> None:
        self._original = original
        self._q = q
        self._buf = ""

    def write(self, s: str) -> int:
        try:
            self._original.write(s)
            self._original.flush()
        except Exception:  # noqa: BLE001
            pass
        self._buf += s
        while "\n" in self._buf:
            line, self._buf = self._buf.split("\n", 1)
            self._q.put(line)
        return len(s)

    def flush(self) -> None:
        try:
            self._original.flush()
        except Exception:  # noqa: BLE001
            pass


def run_pipeline_with_live_logs(*, doc, model, do_verify, concurrency, log_box):
    """Run async pipeline on a worker thread; tail stdout into log_box.

    Returns (result_or_none, captured_log_lines). Re-raises whatever the
    worker thread caught so the main thread can branch on the error type.
    """
    q: "_queue.Queue[str | None]" = _queue.Queue()
    captured: list[str] = []
    result_holder: list = []
    err_holder: list[BaseException] = []

    def _worker():
        original_stdout, original_stderr = sys.stdout, sys.stderr
        try:
            sys.stdout = _LineTee(original_stdout, q)
            sys.stderr = _LineTee(original_stderr, q)
            result = asyncio.run(run_extraction(
                doc, model=model, do_verify=do_verify, concurrency=concurrency,
            ))
            result_holder.append(result)
        except BaseException as e:  # noqa: BLE001
            err_holder.append(e)
        finally:
            sys.stdout, sys.stderr = original_stdout, original_stderr
            q.put(None)

    t = _threading.Thread(target=_worker, daemon=True)
    t.start()

    LIVE_TAIL_LINES = 60
    while True:
        try:
            line = q.get(timeout=0.4)
        except _queue.Empty:
            if not t.is_alive():
                break
            continue
        if line is None:
            break
        captured.append(line)
        log_box.code("\n".join(captured[-LIVE_TAIL_LINES:]), language="text")
        _time.sleep(0.01)

    t.join(timeout=2.0)
    if err_holder:
        raise err_holder[0]
    return result_holder[0] if result_holder else None, captured


def _slugify(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", s.lower()) or "company"


# ---------------------------------------------------------------------------
# Page setup
# ---------------------------------------------------------------------------

st.set_page_config(
    page_title="POC2 — Per-Metric Cached Extractor",
    page_icon="🎯",
    layout="wide",
)
st.title("POC2 — Cached Per-Metric Financial Extractor")
st.caption(
    "Upload an annual report PDF; the pipeline uploads it once, pins a Gemini "
    "context cache (system instruction + PDF), and dispatches one targeted "
    "call per metric. No images, no per-window JSON, nothing persisted on "
    "disk — the cache and the upload are torn down after the result is shown."
)

# Session-state slots. Initialized once per browser session; persists across
# every rerun (download clicks, sidebar interactions) until the user runs a
# fresh extraction or hits "Clear results".
_SS_DEFAULTS: dict[str, object] = {
    "poc2_result": None,         # ExtractionResult dataclass
    "poc2_logs": [],             # list[str] — captured stdout/stderr
    "poc2_year_stem": "",        # str — used in download filenames
    "poc2_company_supplied": False,
    "poc2_size_mb": 0.0,
}
for _k, _v in _SS_DEFAULTS.items():
    st.session_state.setdefault(_k, _v)


with st.sidebar:
    st.header("Inputs")
    company_input = st.text_input(
        "Company name (optional)",
        placeholder="e.g. Jyothy Labs Limited",
        help="Optional. If provided, it's embedded in the cached system "
             "instruction so the model anchors on this entity. Leave blank "
             "to let the model identify the entity from the document itself.",
    )
    pdf_upload = st.file_uploader(
        "PDF (filename should include the year, e.g. AR-2023.pdf)",
        type=["pdf"],
        help="Year is derived from the digits in the filename. "
             "Used only to anchor the temporal column in the prompt.",
    )

    st.markdown("---")
    st.header("Pipeline settings")
    model_labels = list(MODEL_OPTIONS.keys())
    model_label = st.selectbox(
        "Gemini model",
        model_labels,
        index=model_labels.index(DEFAULT_MODEL_LABEL),
        help="Caching is supported on Gemini 2.5+ flash/pro lines. If a model "
             "rejects `cached_content` the SDK will surface a 4xx — swap models "
             "and rerun.",
    )
    selected_model = MODEL_OPTIONS[model_label]
    st.caption(f"`{selected_model}`")

    concurrency = st.slider(
        "Concurrent metrics",
        min_value=1, max_value=8, value=4,
        help="How many per-metric calls run in parallel against the same cache. "
             "Higher = faster, but more prone to 429s on tight quotas.",
    )
    do_verify = st.checkbox(
        "Run verification layer",
        value=False,
        help="For each extracted row, re-ask the cached model whether a more "
             "adjusted figure was available nearby. Roughly doubles latency "
             "and cost for the extraction step.",
    )
    submit = st.button("Run extraction", type="primary", use_container_width=True)

    if st.session_state.poc2_result is not None:
        if st.button("Clear results", use_container_width=True,
                     help="Remove the cached extraction from this session so "
                          "the home screen comes back."):
            for k, v in _SS_DEFAULTS.items():
                st.session_state[k] = v
            st.rerun()

    st.caption(
        "POC2 stores nothing on disk between runs. The uploaded PDF is held "
        "in a tempfile only for the duration of the call."
    )


# ---------------------------------------------------------------------------
# Extraction pass — runs ONLY on the script-run where the user clicked Submit.
# On success, the result is parked in st.session_state and rendered below.
# ---------------------------------------------------------------------------

if submit:
    if pdf_upload is None:
        st.error("Please upload a PDF.")
        st.stop()

    year_stem = derive_year_from_filename(pdf_upload.name)
    if year_stem is None:
        st.error(
            f"Could not derive a year from the filename '{pdf_upload.name}'. "
            "Include digits (e.g. `AR-2023.pdf`, `23.pdf`, `FY24.pdf`)."
        )
        st.stop()

    effective_company = (
        company_input.strip() or "the company in this document"
    )
    pdf_bytes = pdf_upload.getvalue()
    file_size_mb = len(pdf_bytes) / (1024 * 1024)

    # Clear any stale result from a previous extraction the moment a fresh
    # run begins. Without this, an error halfway through the new run would
    # leave the user staring at the previous document's results on the next
    # rerun — quietly wrong. After this point, session_state.poc2_result is
    # None until the new extraction stores its own result below.
    for _k, _v in _SS_DEFAULTS.items():
        st.session_state[_k] = _v

    with temp_pdf(pdf_bytes) as tmp_pdf_path:
        doc = derive_paths(
            tmp_pdf_path,
            company_name=effective_company,
            year_stem=year_stem,
        )

        new_result = None
        captured_logs: list[str] = []
        try:
            with st.status("Running pipeline…", expanded=True) as status:
                status.write(
                    f"Model: `{selected_model}`  ·  concurrency: `{concurrency}`  "
                    f"·  verify: `{do_verify}`"
                )
                status.write(
                    "Uploading PDF, creating cache, then issuing 37 per-metric calls."
                )
                status.write("**Live pipeline log** (last 60 lines):")
                log_box = status.empty()
                new_result, captured_logs = run_pipeline_with_live_logs(
                    doc=doc,
                    model=selected_model,
                    do_verify=do_verify,
                    concurrency=concurrency,
                    log_box=log_box,
                )
                if new_result is None:
                    status.update(label="No result returned.", state="error")
                    st.stop()
                status.update(
                    label=f"Done — {new_result.totals['metrics_found']}/"
                          f"{new_result.totals['metrics_total']} metrics, "
                          f"{new_result.totals['extractions_total']} "
                          f"extraction(s) in "
                          f"{new_result.totals['elapsed_seconds']}s",
                    state="complete",
                )
        except NonRetryablePOC2Failure as e:
            st.error(
                "**Pipeline aborted on a non-retryable error.** Most often: "
                "API key, quota, malformed cache content, or model-not-found. "
                "Fix the underlying issue and re-run."
            )
            st.code(str(e), language="text")
            if captured_logs:
                with st.expander("Pipeline log so far"):
                    st.code("\n".join(captured_logs), language="text")
            st.stop()
        except Exception as e:  # noqa: BLE001
            st.error(f"**Unexpected error:** `{type(e).__name__}: {e}`")
            with st.expander("Full traceback"):
                import traceback as _tb
                st.code(_tb.format_exc(), language="text")
            if captured_logs:
                with st.expander("Pipeline log so far"):
                    st.code("\n".join(captured_logs), language="text")
            st.stop()

        # Park the result in session_state so download clicks / sidebar
        # interactions don't wipe it. The tempfile is unlinked at the end of
        # this `with temp_pdf` block — that's expected. ExtractionResult is a
        # plain dataclass of JSON-ish primitives, so it survives reruns cleanly.
        st.session_state.poc2_result = new_result
        st.session_state.poc2_logs = captured_logs
        st.session_state.poc2_year_stem = year_stem
        st.session_state.poc2_company_supplied = bool(company_input.strip())
        st.session_state.poc2_size_mb = file_size_mb


# ---------------------------------------------------------------------------
# Render pass — runs on EVERY script execution. If session_state doesn't have
# a result yet, show the home/info banner; otherwise render the cached result.
# ---------------------------------------------------------------------------

result = st.session_state.poc2_result
captured_logs = st.session_state.poc2_logs
year_stem = st.session_state.poc2_year_stem
company_supplied = st.session_state.poc2_company_supplied
file_size_mb = st.session_state.poc2_size_mb

if result is None:
    st.info("Upload a PDF (optionally enter a company name) and press "
            "**Run extraction**.")
    st.stop()


# Show a small banner if this isn't the run that produced the result —
# helps the user notice they're looking at cached output after a download click.
if not submit:
    st.caption(
        "Showing cached results from the most recent extraction in this session. "
        "Click **Clear results** in the sidebar to return to the upload screen, "
        "or run a new extraction to overwrite."
    )

company_note = "" if company_supplied else "  *(no company name supplied)*"
st.write(f"**Company:** {result.company_display}{company_note}  |  "
         f"**FY:** {result.fy_year}  |  **Size:** {file_size_mb:.1f} MB")


c1, c2, c3, c4 = st.columns(4)
c1.metric("Metrics found",
          f"{result.totals['metrics_found']} / {result.totals['metrics_total']}")
c2.metric(
    "Extractions",
    result.totals["extractions_total"],
    delta=(
        f"-{result.consolidated_filter_stats['dropped_non_consolidated']} "
        "non-Consolidated"
        if result.consolidated_filter_stats.get("consolidated_present")
        else None
    ),
    delta_color="off",
)
c3.metric("Tokens in/out (extr)",
          f"{result.totals['tokens_in_extraction']:,} / "
          f"{result.totals['tokens_out_extraction']:,}")
c4.metric("Cache hits (tokens)", f"{result.totals['tokens_cached_hits']:,}")

# Entity-scope filter banner
cf = result.consolidated_filter_stats
if cf.get("consolidated_present"):
    st.info(
        f"**Entity scope:** Consolidated rows present → kept "
        f"{cf['rows_out']} Consolidated rows, dropped "
        f"{cf['dropped_non_consolidated']} Standalone/Unclear rows. "
        f"(Rule: when a report publishes consolidated statements, "
        f"standalone figures describe just the parent entity — the "
        f"consolidated set is the company-level truth.)"
    )
elif cf.get("rows_out", 0) > 0:
    st.info(
        "**Entity scope:** No Consolidated rows found — keeping the "
        f"{cf['rows_out']} Standalone / Unclear row(s) as-is."
    )

# Downloads — produced in memory; user saves locally if they want a trail.
download_basename = f"{_slugify(result.company_display)}_{year_stem}_poc2"
full_payload = _json.dumps({
    "company": result.company_display,
    "fy_year": result.fy_year,
    "model": result.model,
    "totals": result.totals,
    "coverage": result.coverage,
    "consolidated_filter_stats": result.consolidated_filter_stats,
    "extractions_raw": result.extractions_raw,
    "extractions": result.extractions,
    "verified": result.verified,
    "per_metric_log": result.per_metric_log,
}, indent=2, ensure_ascii=False).encode("utf-8")

extractions_payload = _json.dumps({
    "company": result.company_display,
    "fy_year": result.fy_year,
    "extractions": result.verified or result.extractions,
}, indent=2, ensure_ascii=False).encode("utf-8")

dl1, dl2, dl3 = st.columns(3)
dl1.download_button(
    "Download full result JSON",
    data=full_payload,
    file_name=f"{download_basename}_full.json",
    mime="application/json",
    use_container_width=True,
    help="Everything: coverage, extractions, optional verified rows, per-metric logs, totals.",
)
dl2.download_button(
    "Download extractions only",
    data=extractions_payload,
    file_name=f"{download_basename}_extractions.json",
    mime="application/json",
    use_container_width=True,
    help="Just the canonical rows (verified version if verification ran).",
)
dl3.download_button(
    "Download pipeline log",
    data=("\n".join(captured_logs)).encode("utf-8") if captured_logs else b"(no logs)",
    file_name=f"{download_basename}.log",
    mime="text/plain",
    use_container_width=True,
    help="Full stdout/stderr from the extraction run.",
)

with st.expander("Full pipeline logs (most recent run)", expanded=False):
    if captured_logs:
        st.code("\n".join(captured_logs), language="text")
    else:
        st.caption("No log lines captured.")


# ---------------------------------------------------------------------------
# Coverage table — clear at-a-glance "what was found vs missed"
# ---------------------------------------------------------------------------

st.divider()
st.subheader(f"Metric coverage — {result.company_display} ({result.fy_year})")

# Build a small dataframe-equivalent via st.dataframe so we don't drag pandas in.
coverage_rows = [{"Metric": name, "Found": "Yes" if found else "No"}
                 for name, found in result.coverage.items()]
st.dataframe(coverage_rows, use_container_width=True, hide_index=True)


# ---------------------------------------------------------------------------
# Extractions — grouped by metric_target
# ---------------------------------------------------------------------------

source_rows = result.verified or result.extractions
if not source_rows:
    st.warning("No metrics were extracted. Try a different model, raise concurrency, "
               "or inspect the per-metric logs for the reason each metric returned null.")
    st.stop()

st.divider()
st.subheader(f"Extracted metrics — {len(source_rows)} disclosure(s)")
if result.verified:
    st.caption("Showing verification-layer output. Rows where `verified: false` "
               "indicate the model recommended a better candidate nearby.")

# Group by metric_target so multiple disclosures collapse into one expander.
by_target: dict[str, list[dict]] = {}
for r in source_rows:
    by_target.setdefault(r.get("metric_target", "—"), []).append(r)

for target, rows in by_target.items():
    n = len(rows)
    suffix = f"  · {n} row{'s' if n != 1 else ''}"
    first_val = rows[0].get("current_year_value", "—")
    first_unit = rows[0].get("declared_unit", "")
    header = f"**{target}** — `{first_val}` {first_unit}{suffix}"
    with st.expander(header):
        for i, m in enumerate(rows, start=1):
            if n > 1:
                st.markdown(f"---\n**Disclosure {i}**")
            verified = m.get("verified")
            verify_note = m.get("verification_note", "")
            cols = st.columns(3)
            cols[0].markdown(f"**Value:** `{m.get('current_year_value', '—')}`")
            cols[1].markdown(f"**Unit:** {m.get('declared_unit', '—')}")
            cols[2].markdown(f"**Page:** {m.get('page_number', '—')}")
            cols2 = st.columns(3)
            cols2[0].markdown(f"**Entity:** {m.get('entity_context', '—')}")
            cols2[1].markdown(f"**Source:** {m.get('source_type', '—')}")
            if verified is not None:
                badge = "✓ verified" if verified else "⚠ correction suggested"
                cols2[2].markdown(f"**Audit:** {badge}")

            verbatim = m.get("verbatim_source_text") or ""
            if verbatim:
                st.markdown("**Verbatim source text:**")
                st.code(verbatim, language="text")
            reasoning = m.get("forensic_reasoning_log") or ""
            if reasoning:
                st.markdown("**Reasoning:**")
                st.write(reasoning)
            if verify_note:
                st.markdown("**Verification note:**")
                st.write(verify_note)
