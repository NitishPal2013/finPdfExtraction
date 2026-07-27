import argparse
import asyncio
import json
import time
import sys
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from POC3.state_manager import PipelineStateDB
from POC3.gemini_client import make_sync_client
from POC3.extractor import run_extraction_from_uri, DEFAULT_MODEL
from POC3.paths import derive_paths

# Target active buffer size for Google API Files
MIN_ACTIVE_BUFFER = 2
MAX_ACTIVE_BUFFER = 5

def _upload_file_sync(local_path: str):
    """Synchronous file upload function to be run in a thread."""
    client = make_sync_client()
    uploaded_file = client.files.upload(file=local_path)
    # Wait for active
    deadline = time.time() + 120.0
    while time.time() < deadline:
        refreshed = client.files.get(name=uploaded_file.name)
        state_str = getattr(refreshed.state, "name", str(getattr(refreshed, "state", None)))
        if "ACTIVE" in state_str:
            return refreshed.name
        if "FAILED" in state_str:
            raise RuntimeError(f"Upload failed: {state_str}")
        time.sleep(2)
    raise TimeoutError(f"Upload timed out for {local_path}")

def _delete_file_sync(gemini_name: str):
    """Synchronous file delete function to be run in a thread."""
    client = make_sync_client()
    client.files.delete(name=gemini_name)

async def upload_service(db: PipelineStateDB):
    """Producer: Keeps the ACTIVE_BUFFER filled."""
    loop = asyncio.get_running_loop()
    with ThreadPoolExecutor(max_workers=MAX_ACTIVE_BUFFER) as pool:
        while True:
            active_count = len(db.get_pdfs_by_status("ACTIVE_BUFFER")) + len(db.get_pdfs_by_status("UPLOADING"))
            if active_count < MAX_ACTIVE_BUFFER:
                needed = MAX_ACTIVE_BUFFER - active_count
                pending = db.get_pdfs_by_status("PENDING", limit=needed)
                
                if pending:
                    for pdf in pending:
                        db.update_status(pdf["local_path"], "UPLOADING")
                    
                    async def upload_task(pdf):
                        print(f"[UploadService] Uploading {Path(pdf['local_path']).name}...")
                        try:
                            gemini_name = await loop.run_in_executor(pool, _upload_file_sync, pdf["local_path"])
                            db.update_status(pdf["local_path"], "ACTIVE_BUFFER", gemini_file_name=gemini_name)
                            print(f"[UploadService] ACTIVE: {Path(pdf['local_path']).name} -> {gemini_name}")
                        except Exception as e:
                            print(f"[UploadService] ERROR uploading {Path(pdf['local_path']).name}: {e}")
                            db.update_status(pdf["local_path"], "ERROR", error_message=str(e))
                            
                    # Fire them off concurrently
                    asyncio.gather(*(upload_task(p) for p in pending))
            
            # Check if everything is done
            counts = db.get_status_counts()
            if counts.get("PENDING", 0) == 0 and counts.get("UPLOADING", 0) == 0:
                break
            await asyncio.sleep(3)

async def extraction_worker(worker_id: int, db: PipelineStateDB, model: str, concurrency: int, out_suffix: str, force: bool):
    """Consumer: Processes ACTIVE_BUFFER files."""
    while True:
        # Get one active file
        active_files = db.get_pdfs_by_status("ACTIVE_BUFFER", limit=1)
        if not active_files:
            counts = db.get_status_counts()
            if counts.get("PENDING", 0) == 0 and counts.get("UPLOADING", 0) == 0 and counts.get("ACTIVE_BUFFER", 0) == 0:
                break
            await asyncio.sleep(2)
            continue
            
        pdf = active_files[0]
        local_path = pdf["local_path"]
        gemini_name = pdf["gemini_file_name"]
        
        # Lock it
        db.update_status(local_path, "PROCESSING")
        
        pdf_path = Path(local_path)
        out_xlsx = pdf_path.parent / f"{pdf_path.stem}{out_suffix}.xlsx"
        out_json = pdf_path.parent / f"{pdf_path.stem}{out_suffix}.json"

        if out_xlsx.exists() and not force:
            print(f"[Worker-{worker_id}] Skipping {pdf_path.name} (already exists).")
            db.update_status(local_path, "PROCESSED_AWAITING_CLEANUP")
            continue

        print(f"[Worker-{worker_id}] Starting extraction on {pdf_path.name}...")
        t0 = time.time()
        try:
            doc_paths = derive_paths(pdf_path, company_name=pdf["company"], fy_override=pdf["fy"])
            result = await run_extraction_from_uri(
                doc_paths, 
                gemini_file_name=gemini_name, 
                model=model, 
                concurrency=concurrency
            )
            
            # Save results
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
                
            print(f"[Worker-{worker_id}] Finished {pdf_path.name} in {time.time() - t0:.1f}s")
            db.update_status(local_path, "PROCESSED_AWAITING_CLEANUP")
            
        except Exception as e:
            print(f"[Worker-{worker_id}] ERROR extracting {pdf_path.name}: {e}")
            db.update_status(local_path, "ERROR", error_message=str(e))

async def janitor_service(db: PipelineStateDB):
    """Cleanup: Deletes files for PROCESSED or ERROR states."""
    loop = asyncio.get_running_loop()
    with ThreadPoolExecutor(max_workers=3) as pool:
        while True:
            cleanup_candidates = db.get_pdfs_by_status("PROCESSED_AWAITING_CLEANUP")
            # Also cleanup errors that have a file uploaded
            error_candidates = [p for p in db.get_pdfs_by_status("ERROR") if p.get("gemini_file_name")]
            
            targets = cleanup_candidates + error_candidates
            
            for pdf in targets:
                # To prevent double deletion attempt, set to DELETING
                db.update_status(pdf["local_path"], "DELETING")
                
                async def delete_task(p):
                    gemini_name = p["gemini_file_name"]
                    try:
                        print(f"[Janitor] Deleting {gemini_name} for {Path(p['local_path']).name}...")
                        await loop.run_in_executor(pool, _delete_file_sync, gemini_name)
                        final_status = "COMPLETED" if p["status"] != "ERROR" else "ERROR"
                        db.update_status(p["local_path"], final_status, gemini_file_name=None)
                        print(f"[Janitor] Cleaned up {Path(p['local_path']).name}")
                    except Exception as e:
                        print(f"[Janitor] Failed to delete {gemini_name}: {e}")
                        
                asyncio.create_task(delete_task(pdf))

            counts = db.get_status_counts()
            active_states = ["PENDING", "UPLOADING", "ACTIVE_BUFFER", "PROCESSING", "PROCESSED_AWAITING_CLEANUP", "DELETING"]
            if all(counts.get(st, 0) == 0 for st in active_states):
                break
            await asyncio.sleep(5)


async def main():
    parser = argparse.ArgumentParser(description="Orchestrator for Decoupled POC3 Pipeline.")
    parser.add_argument("--company-dir", required=True, help="Path to company folder containing PDFs")
    parser.add_argument("--model", default=DEFAULT_MODEL, help="Gemini model name")
    parser.add_argument("--llm-workers", type=int, default=1, help="Number of concurrent PDFs to process at once")
    parser.add_argument("--concurrency", type=int, default=4, help="Metrics concurrency inside each PDF")
    parser.add_argument("--force", action="store_true", help="Overwrite existing workbooks")
    parser.add_argument("--out-suffix", required=False, default="_POC3", help="Suffix for output files")
    args = parser.parse_args()

    company_dir = Path(args.company_dir).resolve()
    if not company_dir.is_dir():
        print(f"Error: {company_dir} is not a directory.")
        sys.exit(1)
        
    company_name = company_dir.name
    pdfs = sorted([p for p in company_dir.glob("*.pdf") if not p.name.endswith("_audit_pages.pdf")])
    
    if not pdfs:
        print(f"No PDFs found in {company_dir}.")
        return

    # Initialize DB
    db = PipelineStateDB()
    for pdf in pdfs:
        # Basic FY extraction (assumes name like 13.pdf -> FY13)
        fy = f"FY{pdf.stem}" if pdf.stem.isdigit() else pdf.stem
        db.add_pdf(company=company_name, fy=fy, local_path=str(pdf))
        
    print(f"=== Starting Orchestrator for {company_name} ({len(pdfs)} PDFs) ===")
    print(f"Target LLM Workers: {args.llm_workers} | Metric Concurrency: {args.concurrency}")
    
    # Spawn background services
    upload_task = asyncio.create_task(upload_service(db))
    janitor_task = asyncio.create_task(janitor_service(db))
    
    # Spawn extraction workers
    worker_tasks = []
    for i in range(args.llm_workers):
        worker_tasks.append(asyncio.create_task(extraction_worker(
            i+1, db, args.model, args.concurrency, args.out_suffix, args.force
        )))
        
    # Wait for everyone to finish
    await upload_task
    await asyncio.gather(*worker_tasks)
    await janitor_task
    
    print("\n=== Pipeline Complete ===")
    counts = db.get_status_counts()
    for status, count in counts.items():
        print(f"  {status}: {count}")

if __name__ == "__main__":
    asyncio.run(main())
