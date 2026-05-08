"""
Streamlit UI for the POC1 financial metric extractor.

Flow:
  1. User uploads a PDF and types a company name.
  2. Year is auto-derived from the uploaded filename (digits).
  3. PDF is saved to  pdfs/<company_slug>/<year>.pdf
  4. `lit screenshot` rasterizes it to pdfs/<company_slug>/<year>_pages/page_*.png
  5. Our Gemini pipeline runs per-window extraction.
  6. Merge dedupes + canonicalizes and we render the final metrics.

Run:  streamlit run POC1/app.py
"""
from __future__ import annotations

import asyncio
import re
import shutil
import sys
from pathlib import Path

# `streamlit run POC1/app.py` puts POC1/ on sys.path, not the project root —
# so `import POC1.*` would fail. Add the project root before any POC1 imports.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import streamlit as st  # noqa: E402

from POC1.merge import merge_for_doc  # noqa: E402
from POC1.paths import derive_paths, ensure_images  # noqa: E402
from POC1.run import (  # noqa: E402
    DEFAULT_MODEL_LABEL,
    MODEL_OPTIONS,
    NonRetryableWindowFailure,
    run as run_extraction,
)

PDFS_ROOT = PROJECT_ROOT / "pdfs"
RESULTS_ROOT = PROJECT_ROOT / "POC1" / "results"


def slugify(name: str) -> str:
    """Company name → directory-safe slug: lowercase alnum, separators stripped."""
    return re.sub(r"[^a-z0-9]+", "", name.lower())


def _path_size(p: Path | None) -> int:
    if p is None or not p.exists():
        return 0
    if p.is_file():
        return p.stat().st_size
    return sum(f.stat().st_size for f in p.rglob("*") if f.is_file())


def _human_size(n: int) -> str:
    size = float(n)
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            return f"{int(size)} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} TB"


def _discover_documents() -> list[dict]:
    """Union scan of pdfs/ and POC1/results/ keyed by (slug, year_stem)."""
    docs: dict[tuple[str, str], dict] = {}

    def _entry(slug: str, stem: str) -> dict:
        key = (slug, stem)
        if key not in docs:
            docs[key] = {
                "slug": slug,
                "year": stem,
                "pdf_path": None,
                "images_dir": None,
                "results_dir": None,
            }
        return docs[key]

    if PDFS_ROOT.exists():
        for company_dir in PDFS_ROOT.iterdir():
            if not company_dir.is_dir():
                continue
            slug = company_dir.name
            for pdf in company_dir.glob("*.pdf"):
                _entry(slug, pdf.stem)["pdf_path"] = pdf
            for sub in company_dir.iterdir():
                if sub.is_dir() and sub.name.endswith("_pages"):
                    _entry(slug, sub.name[: -len("_pages")])["images_dir"] = sub

    if RESULTS_ROOT.exists():
        for r in RESULTS_ROOT.iterdir():
            if not r.is_dir() or "_" not in r.name:
                continue
            slug, stem = r.name.rsplit("_", 1)
            _entry(slug, stem)["results_dir"] = r

    out = []
    for d in docs.values():
        d["pdf_size"] = _path_size(d["pdf_path"])
        d["images_size"] = _path_size(d["images_dir"])
        d["results_size"] = _path_size(d["results_dir"])
        d["display"] = d["slug"].replace("_", " ").replace("-", " ").title() or d["slug"]
        out.append(d)
    return sorted(out, key=lambda x: (x["slug"], x["year"]))


def _remove_path(p: Path | None) -> None:
    if p is None or not p.exists():
        return
    if p.is_file():
        p.unlink()
    else:
        shutil.rmtree(p)


def _wipe_directory_contents(root: Path) -> None:
    if not root.exists():
        return
    for child in root.iterdir():
        _remove_path(child)


# ---------------------------------------------------------------------------
# Live log tailing for the long-running asyncio.run(...) call.
#
# The pipeline emits per-window progress via plain `print()` (so the same
# logs show up in `docker logs`). When invoked from Streamlit we want the
# user to see those lines live in the browser — but `asyncio.run()` blocks
# the main Streamlit thread, so a naive in-line approach renders nothing
# until completion.
#
# Trick: run the asyncio.run() on a worker thread, redirect its stdout +
# stderr to a queue via a tee, and let the main thread drain that queue
# inside the `with st.status(...)` block. The main thread's brief sleeps
# between drains let Streamlit flush partial renders to the browser.
# ---------------------------------------------------------------------------
import contextlib as _contextlib  # noqa: E402
import queue as _queue  # noqa: E402
import threading as _threading  # noqa: E402
import time as _time  # noqa: E402


class _LineTee:
    """File-like object that fans `write()` calls to:
      (a) the original stream (so docker logs / the terminal still see them), and
      (b) a queue, line-by-line, for the Streamlit thread to drain.
    """
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


def run_extraction_with_live_logs(doc, *, model: str, status, log_box):
    """Run the async pipeline on a background thread; tail its stdout into the
    Streamlit `log_box` placeholder. Returns the captured log lines on success;
    re-raises whatever the worker thread caught."""
    q: "_queue.Queue[str | None]" = _queue.Queue()
    captured: list[str] = []
    err_box: list[BaseException] = []

    def _worker():
        original_stdout, original_stderr = sys.stdout, sys.stderr
        try:
            sys.stdout = _LineTee(original_stdout, q)
            sys.stderr = _LineTee(original_stderr, q)
            asyncio.run(run_extraction(doc, model=model))
        except BaseException as e:  # noqa: BLE001
            err_box.append(e)
        finally:
            sys.stdout, sys.stderr = original_stdout, original_stderr
            q.put(None)  # sentinel

    t = _threading.Thread(target=_worker, daemon=True)
    t.start()

    # Drain loop: pull lines from the queue, append, redraw the tail in the UI.
    # `log_box.code(...)` rerenders the whole code block each call — we keep
    # only the last 60 lines on screen to avoid runaway DOM cost on long runs.
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
        log_box.code(
            "\n".join(captured[-LIVE_TAIL_LINES:]),
            language="text",
        )
        # Tiny yield so Streamlit can flush a partial render.
        _time.sleep(0.01)

    t.join(timeout=2.0)
    if err_box:
        raise err_box[0]
    return captured


def _wipe_all_storage() -> None:
    """Button callback — safe to mutate widget-bound session_state here.

    Streamlit disallows mutating session_state keys tied to widgets after the
    widget has been instantiated in the same script run. on_click callbacks
    fire between runs, so this is the correct place to reset the confirm box.
    """
    _wipe_directory_contents(PDFS_ROOT)
    _wipe_directory_contents(RESULTS_ROOT)
    st.session_state["wipe_all_confirm"] = False


def derive_year_from_filename(filename: str) -> str | None:
    """Return a 2-digit year stem from filename digits, or None if none present."""
    digits = re.sub(r"\D", "", Path(filename).stem)
    if not digits:
        return None
    return digits[-2:]


st.set_page_config(
    page_title="Forensic Metric Extractor",
    page_icon="📊",
    layout="wide",
)
st.title("Forensic Financial Metric Extractor")
st.caption(
    "Upload an annual report PDF; the pipeline screenshots each page with `lit`, "
    "runs the 37-target forensic sweeper on sliding windows, and returns only the "
    "explicitly disclosed metrics."
)

with st.sidebar:
    st.header("Inputs")
    company_input = st.text_input(
        "Company name",
        placeholder="e.g. Jyothy Labs Limited",
        help="Shown to the model and used for the directory slug.",
    )
    pdf_upload = st.file_uploader(
        "PDF (filename must include the year, e.g. AR-2023.pdf)",
        type=["pdf"],
        help="Year is derived from the digits in the filename.",
    )
    model_labels = list(MODEL_OPTIONS.keys())
    model_label = st.selectbox(
        "Gemini model",
        model_labels,
        index=model_labels.index(DEFAULT_MODEL_LABEL),
        help="If you hit RESOURCE_EXHAUSTED (quota) on one model, try another. "
             "Each Gemini model line has a separate quota bucket.",
    )
    selected_model = MODEL_OPTIONS[model_label]
    st.caption(f"`{selected_model}`")
    submit = st.button("Run extraction", type="primary", use_container_width=True)

    with st.expander("Manage storage", expanded=False):
        docs = _discover_documents()
        total_bytes = sum(
            d["pdf_size"] + d["images_size"] + d["results_size"] for d in docs
        )
        st.caption(
            f"{len(docs)} document(s) on disk  ·  {_human_size(total_bytes)} total"
        )

        if not docs:
            st.caption("No stored documents yet.")
        else:
            for d in docs:
                total = d["pdf_size"] + d["images_size"] + d["results_size"]
                st.markdown(
                    f"**{d['display']}** — `{d['year']}`  ·  {_human_size(total)}"
                )
                st.caption(
                    f"PDF {_human_size(d['pdf_size'])}  ·  "
                    f"Screenshots {_human_size(d['images_size'])}  ·  "
                    f"Results {_human_size(d['results_size'])}"
                )
                col_r, col_d = st.columns(2)
                clear_key = f"clear_res_{d['slug']}_{d['year']}"
                delete_key = f"del_doc_{d['slug']}_{d['year']}"
                if col_r.button(
                    "Clear results",
                    key=clear_key,
                    disabled=d["results_size"] == 0,
                    use_container_width=True,
                    help="Deletes extraction output only. PDF + screenshots stay so the "
                         "next run re-invokes Gemini on the same pages.",
                ):
                    _remove_path(d["results_dir"])
                    st.rerun()
                if col_d.button(
                    "Delete document",
                    key=delete_key,
                    use_container_width=True,
                    help="Removes PDF, screenshots, and results for this document.",
                ):
                    _remove_path(d["pdf_path"])
                    _remove_path(d["images_dir"])
                    _remove_path(d["results_dir"])
                    # Clean up now-empty company directory
                    if d["pdf_path"] is not None:
                        parent = d["pdf_path"].parent
                        if parent.exists() and parent.is_dir() and not any(parent.iterdir()):
                            parent.rmdir()
                    st.rerun()
                st.divider()

        st.markdown("---")
        st.caption(
            "Danger zone: wipes every stored PDF, screenshot, and result directory."
        )
        confirm_wipe = st.checkbox(
            "I understand — wipe all storage", key="wipe_all_confirm"
        )
        st.button(
            "Clear ALL storage",
            disabled=not confirm_wipe,
            use_container_width=True,
            on_click=_wipe_all_storage,
        )

if not submit:
    st.info("Enter a company name, upload a PDF, and press **Run extraction**.")
    st.stop()

if not company_input.strip():
    st.error("Please enter a company name.")
    st.stop()
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

company_slug = slugify(company_input)
if not company_slug:
    st.error("Company name must contain at least one alphanumeric character.")
    st.stop()

pdf_dir = PDFS_ROOT / company_slug
pdf_dir.mkdir(parents=True, exist_ok=True)
pdf_path = pdf_dir / f"{year_stem}.pdf"
pdf_path.write_bytes(pdf_upload.getvalue())

doc = derive_paths(pdf_path, company_override=company_input.strip())

st.write(f"**Company:** {doc.company_display}  |  **FY:** {doc.fy_year}")
st.write(f"**Saved PDF:** `{doc.pdf_path.relative_to(PROJECT_ROOT)}`")

try:
    with st.status("Running pipeline…", expanded=True) as status:
        status.write(f"Model: `{selected_model}`")
        status.write("Rasterizing PDF with `lit screenshot`…")
        image_dir, n_pages = ensure_images(doc.pdf_path, doc.image_dir)
        status.write(f"→ {n_pages} pages available at `{image_dir.relative_to(PROJECT_ROOT)}`")

        status.write(
            "Running Gemini extraction across sliding windows. "
            "Each window retries indefinitely on transient errors; the run "
            "resumes from completed windows on restart."
        )
        status.write("**Live pipeline log** (last 60 lines):")
        log_box = status.empty()
        # Each click spins up a fresh asyncio loop on a worker thread so that
        # the main Streamlit thread can keep tailing stdout into log_box.
        captured_logs = run_extraction_with_live_logs(
            doc, model=selected_model, status=status, log_box=log_box,
        )

        status.write("Merging + canonicalizing results…")
        result = merge_for_doc(doc.output_dir, doc.merged_path)

        status.update(
            label=f"Done — {result['canonical_metric_count']} metrics extracted "
                  f"from {result['target_coverage']['total_targets']} targets",
            state="complete",
        )
except NonRetryableWindowFailure as e:
    st.error(
        "**Pipeline aborted on a non-retryable error.**\n\n"
        "A window hit an error that won't be fixed by retrying (e.g. auth, "
        "bad request, model not found). The full traceback is in the per-window "
        "JSON under `attempt_log`. Fix the underlying issue and click **Run extraction** "
        "again — completed windows will be skipped automatically."
    )
    st.code(str(e), language="text")
    st.caption(
        f"Per-window logs: `{doc.output_dir.relative_to(PROJECT_ROOT)}/`"
    )
    st.stop()
except Exception as e:  # noqa: BLE001
    # Catch-all so the user sees a friendly message instead of a raw traceback.
    st.error(f"**Unexpected error:** `{type(e).__name__}: {e}`")
    st.caption(
        "This is most often a network/upload failure or a missing dependency "
        "(e.g. `lit` CLI not on PATH). Re-running the pipeline will resume "
        "from the last successful window."
    )
    with st.expander("Full traceback"):
        import traceback as _tb
        st.code(_tb.format_exc(), language="text")
    st.stop()

canonical = result.get("canonical_metrics", [])
coverage = result["target_coverage"]

c1, c2, c3 = st.columns(3)
c1.metric("Metrics found", result["canonical_metric_count"])
c2.metric(
    "Targets covered",
    f"{coverage['found_count']} / {coverage['total_targets']}",
)
c3.metric("Windows processed", result["windows_processed"])

import json as _json  # local import to avoid bloating top-of-module
download_basename = f"{doc.company_slug}_{doc.year_stem}"
full_payload = _json.dumps(result, indent=2, ensure_ascii=False).encode("utf-8")
canonical_payload = _json.dumps(
    {
        "company": doc.company_display,
        "fy_year": doc.fy_year,
        "canonical_metrics": canonical,
        "target_coverage": coverage,
    },
    indent=2,
    ensure_ascii=False,
).encode("utf-8")

dl1, dl2, dl3 = st.columns(3)
dl1.download_button(
    "Download full merged.json",
    data=full_payload,
    file_name=f"{download_basename}_merged.json",
    mime="application/json",
    use_container_width=True,
    help="Full pipeline output — raw rows, dedup stats, cross-row filter stats, "
         "canonical metrics, and target coverage.",
)
dl2.download_button(
    "Download canonical metrics only",
    data=canonical_payload,
    file_name=f"{download_basename}_canonical.json",
    mime="application/json",
    use_container_width=True,
    help="Just the final per-target rows + coverage summary.",
)
dl3.download_button(
    "Download pipeline logs",
    data=("\n".join(captured_logs)).encode("utf-8") if captured_logs else b"(no logs)",
    file_name=f"{download_basename}_pipeline.log",
    mime="text/plain",
    use_container_width=True,
    help="Full stdout/stderr from the extraction run — exactly what you'd "
         "see in `docker logs poc1-extractor`.",
)

with st.expander("Full pipeline logs (this run)", expanded=False):
    if captured_logs:
        st.code("\n".join(captured_logs), language="text")
    else:
        st.caption("No log lines captured.")

if not canonical:
    st.warning("No metrics were extracted. Check the prompt, the PDF, or the window logs.")
    st.stop()

st.divider()
st.subheader(f"Extracted metrics — {doc.company_display} ({doc.fy_year})")

for m in canonical:
    target = m.get("metric_target", "—")
    value = m.get("current_year_value", "—")
    unit = m.get("declared_unit", "")
    ctx = m.get("entity_context", "—")
    src = m.get("source_type", "—")
    header = f"**{target}** — `{value}` {unit}   ·   *{ctx}* · *{src}*"
    with st.expander(header):
        pages = m.get("pages") or [m.get("page_number")]
        st.markdown(f"**Pages:** {', '.join(str(p) for p in pages)}")
        verbatim = m.get("verbatim_source_text", "")
        if verbatim:
            st.markdown("**Verbatim source text:**")
            st.code(verbatim, language="text")
        surrounding = m.get("surrounding_context", "")
        if surrounding:
            st.markdown("**Surrounding context:**")
            st.code(surrounding, language="text")
        reasoning = m.get("forensic_reasoning_log") or m.get("forensic_reasoning") or ""
        if reasoning:
            st.markdown("**Reasoning:**")
            st.write(reasoning)
        alt = [a for a in (m.get("alt_anchors") or []) if a]
        if alt:
            st.markdown("**Other anchors for the same value:**")
            for a in alt:
                st.code(a, language="text")
