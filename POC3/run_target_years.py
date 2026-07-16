#!/usr/bin/env python3
import subprocess
import concurrent.futures
import time
import os

PDF_DIR = "/Users/fti/personal_work/nair/pdfs/Jindal Saw Ltd"
YEARS = [
    ("13.pdf", "FY13"),
    ("16.pdf", "FY16"),
    ("18.pdf", "FY18"),
    ("21.pdf", "FY21"),
]

def run_extraction(item):
    pdf_file, fy = item
    pdf_path = os.path.join(PDF_DIR, pdf_file)
    cmd = [
        "python3",
        "/Users/fti/personal_work/nair/POC3/extractor.py",
        "--pdf", pdf_path,
        "--company", "Jindal Saw Ltd",
        "--year", fy,
        "--model", "gemini-3.1-flash-lite",
        "--concurrency", "4",
        "--force"
    ]
    print(f"[{time.strftime('%X')}] Starting POC3 extraction for {fy} ({pdf_file})...", flush=True)
    start_t = time.time()
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, check=True)
        elapsed = time.time() - start_t
        print(f"[{time.strftime('%X')}] ✅ Finished {fy} in {elapsed:.1f}s!", flush=True)
        return (fy, True, elapsed, res.stdout)
    except subprocess.CalledProcessError as e:
        elapsed = time.time() - start_t
        print(f"[{time.strftime('%X')}] ❌ Failed {fy} after {elapsed:.1f}s!\n{e.stderr}", flush=True)
        return (fy, False, elapsed, e.stderr)

def main():
    print("=== STARTING TARGETED POC3 EXTRACTION (FY13, FY16, FY18, FY21) ===", flush=True)
    start_total = time.time()
    results = []
    # Using 2 concurrent workers to keep API throughput high without hitting rate limits
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        futures = {executor.submit(run_extraction, yr): yr for yr in YEARS}
        for future in concurrent.futures.as_completed(futures):
            results.append(future.result())
            
    print("\n=== TARGETED EXECUTION SUMMARY ===", flush=True)
    for fy, success, elapsed, _ in sorted(results, key=lambda x: x[0]):
        status = "✅ SUCCESS" if success else "❌ FAILED"
        print(f"{fy}: {status} ({elapsed:.1f}s)")
        
    total_elapsed = time.time() - start_total
    print(f"\nTotal Batch Elapsed Time: {total_elapsed:.1f}s ({total_elapsed/60:.1f} mins)", flush=True)

if __name__ == "__main__":
    main()
