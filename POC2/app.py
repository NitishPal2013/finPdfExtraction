"""
Streamlit UI for the POC2 financial metric extractor.

Minimalist UX: company name + PDF upload + one button. Model, concurrency,
and verification are all pinned in code (EXTRACTION_* constants below) so a
non-technical user sees no knobs. Backend events still print to server
stdout (visible in `docker logs`) — they are intentionally NOT surfaced in
the browser, which kept the UI noisy and previously caused long runs to
appear "frozen" while verification was happening.

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

Atomic-swap rule: we DO NOT clear session_state when a fresh run starts. The
new ExtractionResult is built into a local variable and only assigned into
session_state once the pipeline succeeds. A failed mid-run leaves whatever
the user had before intact instead of dropping them onto a blank page.
"""
from __future__ import annotations

import asyncio
import json as _json
import re
import sys
import time
from pathlib import Path

# `streamlit run POC2/app.py` puts POC2/ on sys.path, not the project root —
# so `import POC2.*` would fail. Add the project root before any POC2 imports.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import streamlit as st  # noqa: E402

from POC2.excel_export import build_excel_workbook  # noqa: E402
from POC2.extractor import (  # noqa: E402
    NonRetryablePOC2Failure,
    run_extraction,
)
from POC2.metrics import METRIC_METADATA  # noqa: E402
from POC2.paths import (  # noqa: E402
    derive_paths,
    derive_year_from_filename,
    temp_pdf,
)

# Hardcoded so non-technical users don't have to think about it. If a future
# need arises (e.g. switching to a larger Pro model for harder docs) flip this
# constant in code — we keep the UI uncluttered.
EXTRACTION_MODEL = "gemini-3.1-flash-lite"
EXTRACTION_CONCURRENCY = 4
# Verification is always on per user direction. It roughly doubles latency on
# big PDFs but catches "wrong-version-of-the-metric" mistakes from the first
# pass, which is the whole point of running the audit.
EXTRACTION_VERIFY = True


def _slugify(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", s.lower()) or "company"


class _CheckpointProgress:
    """Translate the extractor's raw event stream into a handful of UI
    checkpoints that a non-technical user can follow.

    The extractor itself emits dozens of events per run — per-metric start
    lines, retry warnings, token-usage breakdowns, cleanup messages — which
    is too noisy for the browser. This callable is wired in as the
    extractor's `progress_callback` and filters those events down to:

      ✓ PDF uploaded (X.X MB)
      ✓ Document prepared for analysis
      ⏳ Extracting financial metrics… N / 37        ← live counter on the label
      ✓ Extracted 37 financial metrics
      ⏳ Verifying figures… N / M                    ← live counter on the label
      ✓ Verified M figures

    Anything that doesn't match a known pattern is forwarded to server
    stdout (visible via `docker logs`) but not surfaced in the UI.
    """

    _METRIC_OK = re.compile(r"^\[M\[.+?\]\] OK — ")
    _VERIFY_START = re.compile(r"^\[verify\] auditing (\d+) extraction")
    _VERIFY_DONE = re.compile(r"^\[V\[.+?\]\] (VERIFIED|CORRECTION)")
    _TOTAL_METRICS = len(METRIC_METADATA)

    def __init__(self, status, file_size_mb: float):
        self.status = status
        self.file_size_mb = file_size_mb
        self.upload_done = False
        self.cache_done = False
        self.extracted = 0
        self.verify_total = 0
        self.verify_done = 0
        self.extracted_announced = False
        # Initial label — replaced as soon as the upload completes.
        status.update(label="⏳ Uploading your document…")

    def __call__(self, msg: str) -> None:
        # Always echo to server stdout so ops/debug visibility survives.
        print(msg, flush=True)

        m = msg.strip()

        if not self.upload_done and m.startswith("[upload] done in"):
            self.upload_done = True
            self.status.write(f"✓ PDF uploaded ({self.file_size_mb:.1f} MB)")
            self.status.update(label="⏳ Preparing document for analysis…")
            return

        if not self.cache_done and m.startswith("[cache] ready in"):
            self.cache_done = True
            self.status.write("✓ Document prepared for analysis")
            self.status.update(
                label=f"⏳ Extracting financial metrics… 0 / {self._TOTAL_METRICS}"
            )
            return

        if self._METRIC_OK.match(m):
            self.extracted += 1
            self.status.update(
                label=(
                    f"⏳ Extracting financial metrics… "
                    f"{self.extracted} / {self._TOTAL_METRICS}"
                )
            )
            return

        verify_start = self._VERIFY_START.match(m)
        if verify_start:
            self.verify_total = int(verify_start.group(1))
            if not self.extracted_announced:
                self.status.write(
                    f"✓ Extracted {self.extracted} financial metrics"
                )
                self.extracted_announced = True
            self.status.update(
                label=f"⏳ Verifying figures… 0 / {self.verify_total}"
            )
            return

        if self._VERIFY_DONE.match(m):
            self.verify_done += 1
            self.status.update(
                label=(
                    f"⏳ Verifying figures… "
                    f"{self.verify_done} / {self.verify_total}"
                )
            )
            return

        # Anything else (banner separators, retries, cleanup) is intentionally
        # not surfaced in the UI — it's already in server stdout.

    def finalize_success(self) -> None:
        """Render the closing ✓ lines once asyncio.run() returns successfully.

        Verification-start might never fire (e.g. extraction returned 0 rows),
        so we guard the 'extracted' checkmark with `extracted_announced` and
        only emit the 'verified' checkmark if verification actually ran.
        """
        if not self.extracted_announced and self.extracted > 0:
            self.status.write(
                f"✓ Extracted {self.extracted} financial metrics"
            )
            self.extracted_announced = True
        if self.verify_total > 0:
            self.status.write(
                f"✓ Verified {self.verify_done} figure(s)"
            )


# ---------------------------------------------------------------------------
# Page setup
# ---------------------------------------------------------------------------

st.set_page_config(
    page_title="POC2 — Per-Metric Cached Extractor",
    page_icon="🎯",
    layout="wide",
)
st.title("Financial Metrics Extractor")
st.caption(
    "Upload an annual report PDF and we'll pull out the key financial "
    "metrics for the reporting year shown in the filename."
)

# Session-state slots. Initialized once per browser session; persists across
# every rerun (download clicks, sidebar interactions) until the user runs a
# fresh extraction or hits "Clear results".
_SS_DEFAULTS: dict[str, object] = {
    "poc2_result": None,         # ExtractionResult dataclass
    "poc2_year_stem": "",        # str — used in download filenames
    "poc2_company_supplied": False,
    "poc2_size_mb": 0.0,
    # Two-phase "running" state. Phase 1 (button click) sets running=True and
    # st.rerun()s; Phase 2 (the next rerun) shows the disabled button + the
    # banner with started_at, then blocks on asyncio.run(). Either path clears
    # the flag before exiting so the UI snaps back to idle.
    "poc2_running": False,
    "poc2_started_at": None,     # float — UNIX timestamp when Phase 1 fired
    "poc2_pending_year_stem": "",  # str — year parsed at Phase 1, used by Phase 2
}
for _k, _v in _SS_DEFAULTS.items():
    st.session_state.setdefault(_k, _v)


with st.sidebar:
    st.header("Inputs")
    company_input = st.text_input(
        "Company name",
        placeholder="e.g. Jyothy Labs Limited",
        help="Required. Embedded in the cached system instruction so the "
             "model anchors on this entity.",
    )
    pdf_upload = st.file_uploader(
        "Annual report PDF",
        type=["pdf"],
        help="Filename should include the year — e.g. `AR-2023.pdf`, "
             "`13.pdf`, `FY24.pdf`. The year is parsed from the digits "
             "and used to pick the right column in the document.",
    )

    # Three pieces of state govern the Run button:
    #   1. Are both required inputs present? (gate)
    #   2. Are we already running a previous click? (lock)
    # The button is enabled only when (1) AND NOT (2).
    company_ready = bool(company_input.strip())
    pdf_ready = pdf_upload is not None
    running_now = st.session_state.poc2_running

    if running_now:
        button_label = "Processing…"
        button_help = (
            "We're processing your document. Please keep this tab open and "
            "don't refresh — refreshing will restart the run."
        )
    else:
        button_label = "Run extraction"
        button_help = (
            None
            if (company_ready and pdf_ready)
            else "Enter a company name and upload a PDF to enable."
        )

    submit = st.button(
        button_label,
        type="primary",
        use_container_width=True,
        disabled=running_now or not (company_ready and pdf_ready),
        help=button_help,
    )

    # Clear button only shown when (a) we have a result to clear AND (b) we're
    # not currently running a fresh extraction (clearing mid-run is confusing).
    if st.session_state.poc2_result is not None and not running_now:
        if st.button("Clear results", use_container_width=True,
                     help="Remove the cached extraction from this session so "
                          "the home screen comes back."):
            for k, v in _SS_DEFAULTS.items():
                st.session_state[k] = v
            st.rerun()


# ---------------------------------------------------------------------------
# Extraction — two-phase rerun.
#
# Phase 1 (this script run): user clicked Run. Validate the filename year,
# flip the `running` flag in session_state, then st.rerun() so the next pass
# starts with the button visibly disabled.
#
# Phase 2 (next script run): `running` is True. Show the disabled button
# (handled in the sidebar block above), render the "started at HH:MM:SS"
# banner + spinner, then block on asyncio.run(). On completion the flag is
# cleared and the result is atomic-swapped into session_state.
# ---------------------------------------------------------------------------

# Phase 1 — fresh click. The button gate guarantees both inputs are present.
if submit and not st.session_state.poc2_running:
    year_stem = derive_year_from_filename(pdf_upload.name)
    if year_stem is None:
        st.error(
            f"Could not read the year from the filename `{pdf_upload.name}`. "
            "Please rename the file to include the report year — for example "
            "`AR-2023.pdf`, `23.pdf`, or `FY24.pdf`."
        )
        st.stop()
    st.session_state.poc2_running = True
    st.session_state.poc2_started_at = time.time()
    st.session_state.poc2_pending_year_stem = year_stem
    st.rerun()

# Phase 2 — execute. We get here on the script rerun immediately after Phase 1
# (and also on any subsequent page reload while the flag is True, since
# session_state survives reruns — see "interrupted-run recovery" below).
if st.session_state.poc2_running:
    # Interrupted-run recovery: if the user reloaded the page mid-run, the
    # file_uploader and text_input may have lost their state. Bail back to
    # the home screen instead of attempting an extraction with no inputs.
    if pdf_upload is None or not company_input.strip():
        for _k, _v in _SS_DEFAULTS.items():
            if _k.startswith("poc2_running") or _k == "poc2_started_at" \
               or _k == "poc2_pending_year_stem":
                st.session_state[_k] = _v
        st.warning(
            "Your previous run was interrupted and the inputs were lost. "
            "Please re-enter the company name and re-upload the PDF, then "
            "press Run extraction again."
        )
        st.stop()

    started_at = st.session_state.poc2_started_at or time.time()
    started_str = time.strftime("%H:%M:%S", time.localtime(started_at))

    year_stem = st.session_state.poc2_pending_year_stem or \
                derive_year_from_filename(pdf_upload.name) or "00"
    effective_company = company_input.strip()
    pdf_bytes = pdf_upload.getvalue()
    file_size_mb = len(pdf_bytes) / (1024 * 1024)

    # Atomic-swap pattern: new result is built in a local variable and only
    # written to session_state on success. A mid-run failure leaves the
    # previous successful result (if any) untouched.
    #
    # The st.status block replaces the previous spinner — its `label` is a
    # live-updating one-liner the user can read at a glance, and each
    # `status.write(...)` from the checkpoint helper appends a ✓ line inside.
    # On completion the whole block collapses to the final status line.
    new_result = None
    with st.status(
        f"⏳ Processing your document — started at {started_str}",
        expanded=True,
    ) as status:
        status.write(
            "Please keep this tab open and avoid refreshing while the run "
            "is in progress."
        )
        progress = _CheckpointProgress(status, file_size_mb)
        try:
            with temp_pdf(pdf_bytes) as tmp_pdf_path:
                doc = derive_paths(
                    tmp_pdf_path,
                    company_name=effective_company,
                    year_stem=year_stem,
                )
                new_result = asyncio.run(run_extraction(
                    doc,
                    model=EXTRACTION_MODEL,
                    do_verify=EXTRACTION_VERIFY,
                    concurrency=EXTRACTION_CONCURRENCY,
                    progress_callback=progress,
                ))

            if new_result is None:
                status.update(
                    label="❌ No result returned",
                    state="error",
                    expanded=True,
                )
                st.session_state.poc2_running = False
                st.session_state.poc2_started_at = None
                st.session_state.poc2_pending_year_stem = ""
                st.error("The pipeline returned no result. Please try again.")
                st.stop()

            # Success — finalize checkpoints, collapse the block, atomic-swap.
            progress.finalize_success()
            status.update(
                label=(
                    f"✅ Done — {new_result.totals['metrics_found']} of "
                    f"{new_result.totals['metrics_total']} metrics extracted "
                    f"in {new_result.totals['elapsed_seconds']:.0f}s"
                ),
                state="complete",
                expanded=False,
            )

            st.session_state.poc2_result = new_result
            st.session_state.poc2_year_stem = year_stem
            st.session_state.poc2_company_supplied = True
            st.session_state.poc2_size_mb = file_size_mb
            st.session_state.poc2_running = False
            st.session_state.poc2_started_at = None
            st.session_state.poc2_pending_year_stem = ""
            st.rerun()

        except NonRetryablePOC2Failure:
            status.update(
                label="❌ Could not process this document",
                state="error",
                expanded=True,
            )
            st.session_state.poc2_running = False
            st.session_state.poc2_started_at = None
            st.session_state.poc2_pending_year_stem = ""
            st.error(
                "We couldn't process this document. This is usually an API "
                "key / quota / model availability issue. Please try again, "
                "or contact support if the problem persists."
            )
            st.stop()
        except Exception as e:  # noqa: BLE001
            status.update(
                label=f"❌ Unexpected error ({type(e).__name__})",
                state="error",
                expanded=True,
            )
            st.session_state.poc2_running = False
            st.session_state.poc2_started_at = None
            st.session_state.poc2_pending_year_stem = ""
            st.error(
                f"Something went wrong while processing this document "
                f"(`{type(e).__name__}`). Please try again."
            )
            st.stop()


# ---------------------------------------------------------------------------
# Render pass — runs on EVERY script execution. If session_state doesn't have
# a result yet, show the home/info banner; otherwise render the cached result.
# ---------------------------------------------------------------------------

result = st.session_state.poc2_result
year_stem = st.session_state.poc2_year_stem
file_size_mb = st.session_state.poc2_size_mb

if result is None:
    st.info(
        "Enter a company name and upload an annual report PDF in the sidebar, "
        "then press **Run extraction**."
    )
    st.stop()


# Show a small banner if this isn't the run that produced the result —
# helps the user notice they're looking at cached output after a download click.
if not submit:
    st.caption(
        "Showing cached results from the most recent extraction in this session. "
        "Click **Clear results** in the sidebar to return to the upload screen, "
        "or run a new extraction to overwrite."
    )

st.write(f"**Company:** {result.company_display}  |  "
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
    "Download Excel (.xlsx)",
    data=build_excel_workbook(result),
    file_name=f"{download_basename}.xlsx",
    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    use_container_width=True,
    help="Multi-sheet workbook: Extractions, Coverage, Summary, Per-Metric Log.",
)



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
    st.warning(
        "No metrics were extracted from this document. The PDF may not contain "
        "the disclosures we look for, or the relevant pages may not be machine-"
        "readable. Try a different annual report."
    )
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
