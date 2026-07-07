"""
Streamlit dashboard for POC3: Two-Stage Exhaustive Candidate Extraction & LLM Finalization Layer.

Features:
  - Sidebar for PDF upload, company/FY config, and concurrency controls.
  - Live execution status log showing Layer 1 harvesting and Layer 2 finalization.
  - Interactive tabs for:
      1) Finalized Disclosures (winning metrics and locations)
      2) Candidate Audit Trail (all candidates found per metric + rejection reasons)
  - One-click downloads for Excel (.xlsx) and JSON (.json).
"""
from __future__ import annotations

import asyncio
import io
import json
import sys as _sys
import tempfile
from pathlib import Path

import pandas as pd
import streamlit as st

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in _sys.path:
    _sys.path.insert(0, str(_PROJECT_ROOT))

from POC3.excel_export import export_to_excel
from POC3.extractor import DEFAULT_MODEL, run_extraction
from POC3.metrics import METRIC_METADATA
from POC3.paths import derive_paths, temp_pdf


st.set_page_config(
    page_title="POC3: Two-Stage Financial Extractor",
    page_icon="🏦",
    layout="wide",
)

st.title("🏦 POC3: Two-Stage Financial Extractor & Audit Engine")
st.markdown(
    """
    **Recall vs. Precision Architecture:**
    1. **Layer 1 (Candidate Harvesting):** Scans the entire document to harvest *all* possible mentions/candidates without premature rejection.
    2. **Layer 2 (LLM Finalization):** Verifies physical page proofs, enforces Consolidated preference, ranks by source type, and picks the winning disclosure.
    """
)

# ── Sidebar Config ───────────────────────────────────────────────────────────
with st.sidebar:
    st.header("1. Document Input")
    uploaded_file = st.file_uploader("Upload Annual Report (PDF)", type=["pdf"])
    company_name = st.text_input("Company Display Name", value="Jindal Saw Ltd")
    fy_year = st.text_input("Target FY / Period", value="FY14")

    st.header("2. Pipeline Config")
    model_choice = st.selectbox(
        "Gemini Model",
        options=["gemini-2.5-flash", "gemini-3.1-flash-lite", "gemini-3.1-flash"],
        index=0,
    )
    concurrency = st.slider("Concurrency Limit", min_value=1, max_value=10, value=4)

    run_btn = st.button("🚀 Run Two-Stage Extraction", type="primary", use_container_width=True)


# ── Main Execution Logic ─────────────────────────────────────────────────────
if run_btn:
    if not uploaded_file:
        st.error("Please upload a PDF file in the sidebar first.")
    else:
        st.session_state.pop("poc3_result", None)
        st.session_state.pop("poc3_excel_bytes", None)
        st.session_state.pop("poc3_json_bytes", None)

        status_box = st.status("Running Two-Stage Pipeline...", expanded=True)
        logs = []

        def progress_cb(msg: str):
            logs.append(msg)
            status_box.write(msg)

        with temp_pdf(uploaded_file.getvalue(), suffix=".pdf") as tmp_path:
            doc_paths = derive_paths(tmp_path, company_name=company_name, fy_override=fy_year)
            try:
                res = asyncio.run(
                    run_extraction(
                        doc_paths,
                        model=model_choice,
                        concurrency=concurrency,
                        progress_callback=progress_cb,
                    )
                )
                status_box.update(label="✅ Extraction & Finalization Complete!", state="complete", expanded=False)
                st.session_state["poc3_result"] = res

                # Generate Excel bytes in memory
                with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as tmp_xlsx:
                    export_to_excel(res, tmp_xlsx.name)
                    with open(tmp_xlsx.name, "rb") as f:
                        st.session_state["poc3_excel_bytes"] = f.read()
                Path(tmp_xlsx.name).unlink(missing_ok=True)

                # Generate JSON bytes in memory
                json_data = {
                    "company": res.company_display,
                    "fy_year": res.fy_year,
                    "model": res.model,
                    "totals": res.totals,
                    "finalized_metrics": res.finalized_metrics,
                    "harvested_candidates": res.harvested_candidates,
                }
                st.session_state["poc3_json_bytes"] = json.dumps(json_data, indent=2).encode("utf-8")

            except Exception as e:
                status_box.update(label="❌ Pipeline Failed!", state="error", expanded=True)
                st.exception(e)

# ── Results Display ──────────────────────────────────────────────────────────
if "poc3_result" in st.session_state:
    res = st.session_state["poc3_result"]
    totals = res.totals

    # Top KPI metrics
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Metrics Found", f"{totals.get('metrics_found', 0)} / {totals.get('metrics_total', 37)}")
    c2.metric("Input Tokens", f"{totals.get('tokens_in', 0):,}")
    c3.metric("Output Tokens", f"{totals.get('tokens_out', 0):,}")
    c4.metric("Elapsed Time", f"{totals.get('elapsed_seconds', 0)}s")

    # Download Buttons
    col_dl1, col_dl2 = st.columns(2)
    with col_dl1:
        if "poc3_excel_bytes" in st.session_state:
            st.download_button(
                label="📥 Download Excel Spreadsheet (.xlsx)",
                data=st.session_state["poc3_excel_bytes"],
                file_name=f"{res.company_display}_{res.fy_year}_POC3.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True,
            )
    with col_dl2:
        if "poc3_json_bytes" in st.session_state:
            st.download_button(
                label="📥 Download Complete Audit JSON (.json)",
                data=st.session_state["poc3_json_bytes"],
                file_name=f"{res.company_display}_{res.fy_year}_POC3.json",
                mime="application/json",
                use_container_width=True,
            )

    st.markdown("---")

    tab1, tab2 = st.tabs(["📊 Finalized Disclosures", "🔍 Candidate Audit Trail & Rejection Log"])

    with tab1:
        st.subheader("Winning Disclosures Selected by Layer 2")
        rows = []
        for item in res.finalized_metrics:
            val = item.get("final_value")
            win = item.get("winning_candidate") or {}
            rows.append({
                "Metric": item.get("metric_target", ""),
                "Value": val if val is not None else "NOT DISCLOSED",
                "Context": win.get("entity_context", "N/A"),
                "Source": win.get("source_type", "N/A"),
                "Page #": win.get("page_number", ""),
                "Printed Page": win.get("printed_page_number", ""),
                "Table/Section": win.get("table_or_section", ""),
                "Fallback?": "YES" if item.get("is_standalone_fallback_active") else "NO",
                "Verbatim Text": win.get("verbatim_source_text", ""),
            })
        df1 = pd.DataFrame(rows)
        st.dataframe(df1, use_container_width=True, hide_index=True)

    with tab2:
        st.subheader("Layer 1 Harvested Pool & Layer 2 Verification Audit")
        st.markdown("Select a metric below to view all candidates discovered across the document and why they were accepted or discarded.")
        
        selected_metric = st.selectbox(
            "Select Metric to Audit",
            options=[m["name"] for m in METRIC_METADATA],
        )

        cand_list = res.harvested_candidates.get(selected_metric, [])
        finalized_obj = next((m for m in res.finalized_metrics if m.get("metric_target") == selected_metric), {})
        audit_log = finalized_obj.get("rejection_audit_log", [])

        st.markdown("#### 📜 Layer 2 Decision Audit Log")
        for log_msg in audit_log:
            if "ACCEPTED" in log_msg:
                st.success(log_msg)
            elif "REJECTED" in log_msg:
                st.error(log_msg)
            else:
                st.info(log_msg)

        st.markdown(f"#### 📦 Layer 1 Harvested Candidates ({len(cand_list)} found)")
        if not cand_list:
            st.warning("No candidate mentions were discovered by Layer 1 anywhere in the document.")
        else:
            for i, cand in enumerate(cand_list, 1):
                with st.expander(f"Candidate #{i}: {cand.get('current_year_value', 'N/A')} ({cand.get('entity_context', 'Unclear')} | {cand.get('source_type', 'N/A')}) — Page {cand.get('page_number', 'N/A')}"):
                    st.markdown(f"**Verbatim Source Text:** `{cand.get('verbatim_source_text', '')}`")
                    st.markdown(f"**Table / Section:** {cand.get('table_or_section', 'N/A')}")
                    st.markdown(f"**Line Above Proof:** `{cand.get('page_verbatim_proof_above', 'N/A')}`")
                    st.markdown(f"**Line Below Proof:** `{cand.get('page_verbatim_proof_below', 'N/A')}`")
                    st.markdown(f"**Printed Page:** {cand.get('printed_page_number', 'N/A')}")
                    st.markdown(f"**Forensic Notes:** *{cand.get('forensic_reasoning_log', 'None')}*")
