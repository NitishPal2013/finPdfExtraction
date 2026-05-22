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
import uuid
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
from POC2.gcs_upload import (  # noqa: E402
    delete_gcs_object,
    gcs_object_exists,
    gcs_pdf_to_temp,
    generate_signed_put_url,
    get_upload_bucket,
)
from POC2.metrics import METRIC_METADATA  # noqa: E402
from POC2.paths import (  # noqa: E402
    derive_paths,
    derive_year_from_filename,
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

      ✓ Sent document to extraction engine
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

    def __init__(self, status):
        self.status = status
        self.upload_done = False
        self.cache_done = False
        self.extracted = 0
        self.verify_total = 0
        self.verify_done = 0
        self.extracted_announced = False
        # Initial label — replaced as soon as the upload completes. We say
        # "extraction engine" rather than "uploading" because the user
        # already uploaded their PDF to cloud storage in the previous step;
        # this is a separate transfer to the Gemini Files API.
        status.update(label="⏳ Sending to extraction engine…")

    def __call__(self, msg: str) -> None:
        # Always echo to server stdout so ops/debug visibility survives.
        print(msg, flush=True)

        m = msg.strip()

        if not self.upload_done and m.startswith("[upload] done in"):
            self.upload_done = True
            self.status.write("✓ Sent document to extraction engine")
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
    "metrics for the reporting year you specify."
)

# GCS bucket bootstrap. We resolve this once at startup so any
# misconfiguration (missing env var, missing perms) surfaces a clear error
# before the user wastes time filling in inputs.
try:
    UPLOAD_BUCKET = get_upload_bucket()
except RuntimeError as e:
    st.error(
        f"**Configuration error.** This app expects an upload bucket to be "
        f"configured.\n\n{e}"
    )
    st.stop()

# Session-state slots. Initialized once per browser session; persists across
# every rerun (download clicks, sidebar interactions) until the user runs a
# fresh extraction or hits "Clear results".
_SS_DEFAULTS: dict[str, object] = {
    "poc2_result": None,         # ExtractionResult dataclass
    "poc2_year_stem": "",        # str — used in download filenames
    "poc2_company_supplied": False,
    "poc2_size_mb": 0.0,
    # Two-phase "trigger" state.
    #
    # Phase 1 (button click) sets `poc2_trigger_extraction=True` and st.rerun()s
    # so the next pass renders with the button visibly disabled.
    #
    # Phase 2 (next script run) reads the trigger, CONSUMES IT IMMEDIATELY
    # (sets it back to False before any work starts), then runs the pipeline.
    # The immediate consumption is critical: if the script is killed mid-pipeline
    # (Cloud Run request timeout → WebSocket drop → browser auto-reconnect →
    # Streamlit re-executes the script with session_state intact), Phase 2
    # MUST NOT re-enter and start a duplicate pipeline. Consuming the trigger
    # on entry makes Phase 2 a one-shot — the very behaviour that lost a
    # pipeline mid-run is now what guarantees we don't restart it.
    #
    # `poc2_pipeline_was_attempted` is set when Phase 2 enters and cleared at
    # the end of either the success or error path. If we see was_attempted=True
    # with trigger=False, we know the run was interrupted (Phase 2 entered but
    # never reached either cleanup path) and can surface a clear message to
    # the user.
    "poc2_trigger_extraction": False,
    "poc2_pipeline_was_attempted": False,
    "poc2_started_at": None,     # float — UNIX timestamp when Phase 1 fired
    "poc2_pending_year_stem": "",  # str — year parsed at Phase 1, used by Phase 2
    # GCS direct-upload session: the JS in the HTML component PUTs to
    # uploads/<upload_id>.pdf using a signed URL we pass in. The id is
    # regenerated after each successful run so a fresh upload always starts
    # clean; we DO NOT regenerate it after an interrupted/failed run so the
    # user can retry without re-uploading their PDF.
    "poc2_upload_id": "",
}
for _k, _v in _SS_DEFAULTS.items():
    st.session_state.setdefault(_k, _v)

# Ensure we always have a non-empty upload id for the JS component to target.
if not st.session_state.poc2_upload_id:
    st.session_state.poc2_upload_id = str(uuid.uuid4())


with st.sidebar:
    st.header("Inputs")
    company_input = st.text_input(
        "Company name",
        placeholder="e.g. Jyothy Labs Limited",
        help="Required. Embedded in the cached system instruction so the "
             "model anchors on this entity.",
    )
    year_input = st.text_input(
        "Annual report year",
        placeholder="e.g. 23 (for FY23 / year ending March 31, 2023)",
        help="Required. Indian Fiscal Year convention — '23' means the year "
             "ending March 31, 2023. You can also type '2023' or 'FY23'.",
    )

    st.markdown("**Annual report PDF**")
    upload_id = st.session_state.poc2_upload_id
    object_name = f"uploads/{upload_id}.pdf"

    # Generate a fresh signed URL on each render. The URL is single-use
    # (scoped to this exact object_name, valid for 30 minutes) so re-rendering
    # is cheap and safe — old URLs simply expire.
    try:
        signed_url = generate_signed_put_url(object_name)
    except Exception as e:  # noqa: BLE001
        st.error(
            f"Couldn't generate an upload URL. This usually means the Cloud "
            f"Run service account is missing IAM permissions on the bucket "
            f"or on itself. See POC2/gcs_upload.py for the required setup.\n\n"
            f"`{type(e).__name__}: {e}`"
        )
        st.stop()

    # HTML+JS component for direct-to-GCS upload. The browser PUTs the file
    # straight to GCS, bypassing Cloud Run's 32 MiB request body cap.
    # sessionStorage persists the "uploaded" flag across Streamlit reruns so
    # typing in the company / year inputs (which retrigger the iframe) doesn't
    # blank out the success state.
    upload_html = f"""
<style>
  .upload-box {{
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    font-size: 13px;
    line-height: 1.5;
  }}
  .upload-box input[type=file] {{
    width: 100%;
    margin-bottom: 8px;
    font-size: 12px;
  }}
  .upload-box button {{
    width: 100%;
    padding: 6px 12px;
    background: #ff4b4b;
    color: white;
    border: none;
    border-radius: 4px;
    cursor: pointer;
    font-weight: 500;
  }}
  .upload-box button:disabled {{
    background: #888;
    cursor: not-allowed;
  }}
  .upload-box .status {{
    margin-top: 10px;
    padding: 8px;
    border-radius: 4px;
    font-size: 12px;
  }}
  .upload-box .status.ok   {{ background: #d4edda; color: #155724; }}
  .upload-box .status.err  {{ background: #f8d7da; color: #721c24; }}
  .upload-box .status.info {{ background: #e2e3e5; color: #383d41; }}
</style>
<div class="upload-box">
  <div id="picker-row">
    <input type="file" id="pdf-file" accept="application/pdf"/>
    <button type="button" id="upload-btn" disabled>Upload to cloud storage</button>
  </div>
  <div id="status" class="status info">Choose a PDF, then click upload.</div>
</div>
<script>
  (function() {{
    const UPLOAD_ID = "{upload_id}";
    const SIGNED_URL = {_json.dumps(signed_url)};
    const storageKey = "poc2_uploaded_" + UPLOAD_ID;

    const picker = document.getElementById('pdf-file');
    const btn = document.getElementById('upload-btn');
    const status = document.getElementById('status');
    const pickerRow = document.getElementById('picker-row');

    // If this upload id was already completed in a prior rerun, restore the
    // success state instead of showing the file picker again.
    if (sessionStorage.getItem(storageKey) === 'true') {{
      pickerRow.style.display = 'none';
      status.className = 'status ok';
      status.textContent = '✓ PDF uploaded. Fill in the inputs at left and click Run extraction.';
      return;
    }}

    function setStatus(cls, text) {{
      status.className = 'status ' + cls;
      status.textContent = text;
    }}

    picker.addEventListener('change', () => {{
      btn.disabled = !picker.files[0];
      if (picker.files[0]) {{
        const mb = (picker.files[0].size / (1024*1024)).toFixed(1);
        setStatus('info', 'Ready to upload: ' + picker.files[0].name + ' (' + mb + ' MB)');
      }}
    }});

    btn.addEventListener('click', async () => {{
      const file = picker.files[0];
      if (!file) return;
      btn.disabled = true;
      picker.disabled = true;
      const mb = (file.size / (1024*1024)).toFixed(1);
      setStatus('info', 'Uploading ' + mb + ' MB to cloud storage…');
      try {{
        const res = await fetch(SIGNED_URL, {{
          method: 'PUT',
          headers: {{ 'Content-Type': 'application/pdf' }},
          body: file,
        }});
        if (res.ok) {{
          sessionStorage.setItem(storageKey, 'true');
          pickerRow.style.display = 'none';
          setStatus('ok', '✓ PDF uploaded (' + mb + ' MB). Fill in the inputs at left and click Run extraction.');
        }} else {{
          const body = await res.text();
          setStatus('err', 'Upload failed: HTTP ' + res.status + '. ' + body.slice(0, 200));
          btn.disabled = false;
          picker.disabled = false;
        }}
      }} catch (e) {{
        setStatus('err', 'Upload failed: ' + e.message);
        btn.disabled = false;
        picker.disabled = false;
      }}
    }});
  }})();
</script>
""".strip()

    st.components.v1.html(upload_html, height=180)

    # Three pieces of state govern the Run button:
    #   1. Are both text inputs present? (company + year — gate)
    #   2. Has the user already clicked and we're transitioning to Phase 2?
    # We DO NOT check the PDF on the Streamlit side because the JS upload
    # happens out-of-band; the server-side existence check happens at the
    # start of Phase 1 below, with a clear error message if the user clicks
    # Run before the upload completes.
    company_ready = bool(company_input.strip())
    year_ready = bool(year_input.strip())
    triggered_now = st.session_state.poc2_trigger_extraction

    if triggered_now:
        button_label = "Processing…"
        button_help = (
            "We're processing your document. Please keep this tab open. "
            "If the run gets interrupted (long pipelines can hit network "
            "timeouts) the page will tell you and you can click Run again."
        )
    else:
        button_label = "Run extraction"
        if not company_ready or not year_ready:
            button_help = "Enter a company name and year to enable."
        else:
            button_help = "Make sure the PDF upload above shows the ✓ before clicking."

    submit = st.button(
        button_label,
        type="primary",
        use_container_width=True,
        disabled=triggered_now or not (company_ready and year_ready),
        help=button_help,
    )

    # Clear button only shown when (a) we have a result to clear AND (b) we're
    # not currently triggering a fresh extraction (clearing mid-trigger is
    # confusing).
    if st.session_state.poc2_result is not None and not triggered_now:
        if st.button("Clear results", use_container_width=True,
                     help="Remove the cached extraction from this session so "
                          "the home screen comes back."):
            for k, v in _SS_DEFAULTS.items():
                st.session_state[k] = v
            # Fresh upload id so the next session starts with a clean picker.
            st.session_state.poc2_upload_id = str(uuid.uuid4())
            st.rerun()


# ---------------------------------------------------------------------------
# Extraction — two-phase rerun, with one-shot trigger semantics.
#
# Phase 1 (this script run): user clicked Run. Validate the year, verify the
# PDF is in GCS, set the trigger flag, then st.rerun() so the next pass
# renders with the disabled button.
#
# Phase 2 (next script run): the trigger is True. CONSUME IT IMMEDIATELY so
# that any subsequent restart of the script (Cloud Run's WebSocket idle
# timeout dropping the connection mid-pipeline → browser auto-reconnect →
# Streamlit re-executes the script with session_state intact) does NOT
# re-enter Phase 2 and start a duplicate pipeline. This single rule is what
# fixes the "extraction restarts at 4/37 after the first run already
# completed" loop the user saw.
# ---------------------------------------------------------------------------


def _clear_extraction_state() -> None:
    """Reset the per-run flags. Called from every error / completion path so
    the next click starts clean."""
    st.session_state.poc2_trigger_extraction = False
    st.session_state.poc2_pipeline_was_attempted = False
    st.session_state.poc2_started_at = None
    st.session_state.poc2_pending_year_stem = ""


# Phase 1 — fresh click.
if submit and not st.session_state.poc2_trigger_extraction:
    # Parse the year from whatever the user typed — '23', '2023', 'FY23'
    # all resolve to year_stem '23' via the same helper that used to read
    # the filename. We reuse it because the parsing semantics are identical.
    year_stem = derive_year_from_filename(year_input)
    if year_stem is None:
        st.error(
            f"Couldn't read a year from `{year_input}`. Please enter the "
            "report year as a 2- or 4-digit number — for example `23`, "
            "`2023`, or `FY23`."
        )
        st.stop()

    # The PDF lives in GCS only if the JS upload completed. Check before
    # transitioning so an over-eager click doesn't silently start an
    # extraction against a missing file.
    object_name = f"uploads/{st.session_state.poc2_upload_id}.pdf"
    try:
        pdf_in_gcs = gcs_object_exists(object_name)
    except Exception as e:  # noqa: BLE001
        st.error(
            f"Couldn't reach cloud storage to verify your upload "
            f"(`{type(e).__name__}: {e}`). Please try again."
        )
        st.stop()
    if not pdf_in_gcs:
        st.error(
            "We don't see your PDF in cloud storage yet. Please wait until "
            "the green ✓ appears under **Annual report PDF** in the sidebar, "
            "then click Run extraction again."
        )
        st.stop()

    st.session_state.poc2_trigger_extraction = True
    st.session_state.poc2_started_at = time.time()
    st.session_state.poc2_pending_year_stem = year_stem
    st.rerun()

# Phase 2 — execute. CONSUME the trigger before anything else. Once consumed,
# any subsequent re-execution of this script (reconnect, refresh, etc.) will
# fall through this block instead of restarting the pipeline.
if st.session_state.poc2_trigger_extraction:
    st.session_state.poc2_trigger_extraction = False
    st.session_state.poc2_pipeline_was_attempted = True

    # Interrupted-run recovery: if the company / year inputs were lost
    # (e.g. session reset between Phase 1 and Phase 2), bail cleanly.
    if not company_input.strip() or not year_input.strip():
        _clear_extraction_state()
        st.warning(
            "Your previous run was interrupted and the inputs were lost. "
            "Please re-enter the company name and year, re-upload the PDF, "
            "then press Run extraction again."
        )
        st.stop()

    object_name = f"uploads/{st.session_state.poc2_upload_id}.pdf"
    started_at = st.session_state.poc2_started_at or time.time()
    started_str = time.strftime("%H:%M:%S", time.localtime(started_at))

    year_stem = st.session_state.poc2_pending_year_stem or \
                derive_year_from_filename(year_input) or "00"
    effective_company = company_input.strip()

    # Atomic-swap pattern: new result is built in a local variable and only
    # written to session_state on success. A mid-run failure leaves the
    # previous successful result (if any) untouched. We DO NOT regenerate
    # the upload_id on failure so the user can retry with the same uploaded
    # PDF; only success regenerates it.
    new_result = None
    file_size_mb = 0.0
    with st.status(
        f"⏳ Processing your document — started at {started_str}",
        expanded=True,
    ) as status:
        status.write(
            "Please keep this tab open while the run is in progress. If the "
            "page does get interrupted, the next view will tell you and you "
            "can click Run extraction again — no need to re-upload."
        )
        try:
            with gcs_pdf_to_temp(object_name) as tmp_pdf_path:
                file_size_mb = tmp_pdf_path.stat().st_size / (1024 * 1024)
                progress = _CheckpointProgress(status)
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
                _clear_extraction_state()
                st.error("The pipeline returned no result. Please try again.")
                st.stop()

            # Success — finalize checkpoints, collapse the block, atomic-swap,
            # tidy up the GCS object (lifecycle rule is the backstop), and
            # regenerate the upload_id so the next run starts with a fresh
            # picker.
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
            delete_gcs_object(object_name)

            st.session_state.poc2_result = new_result
            st.session_state.poc2_year_stem = year_stem
            st.session_state.poc2_company_supplied = True
            st.session_state.poc2_size_mb = file_size_mb
            _clear_extraction_state()
            st.session_state.poc2_upload_id = str(uuid.uuid4())
            st.rerun()

        except NonRetryablePOC2Failure:
            status.update(
                label="❌ Could not process this document",
                state="error",
                expanded=True,
            )
            _clear_extraction_state()
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
            _clear_extraction_state()
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

# Interrupted-run banner. If we get here with `was_attempted=True` and the
# trigger is False (already consumed), Phase 2 entered the pipeline but
# never reached either the success or error cleanup path. The most common
# cause is Cloud Run's request timeout dropping the WebSocket mid-pipeline.
# Surface this clearly instead of silently dropping the user on a blank page.
if (st.session_state.poc2_pipeline_was_attempted
        and not st.session_state.poc2_trigger_extraction):
    st.session_state.poc2_pipeline_was_attempted = False  # one-shot
    st.warning(
        "**Your previous extraction was interrupted before it could finish.** "
        "This usually means the run took longer than the cloud platform's "
        "request timeout (typically 5 minutes). Your uploaded PDF is still "
        "in cloud storage, so just click **Run extraction** again — no need "
        "to re-upload. For very long PDFs, ask your administrator to raise "
        "the Cloud Run request timeout."
    )

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
