#!/usr/bin/env python3
import subprocess
import concurrent.futures
import time
import os

RUNS = [
    ("/Users/fti/personal_work/nair/pdfs/Zomato Ltd/22.pdf", "Zomato Ltd", "FY22"),
    ("/Users/fti/personal_work/nair/pdfs/Zomato Ltd/23.pdf", "Zomato Ltd", "FY23"),
    ("/Users/fti/personal_work/nair/pdfs/Vodafone Idea Ltd/13.pdf", "Vodafone Idea Ltd", "FY13"),
    ("/Users/fti/personal_work/nair/pdfs/Vodafone Idea Ltd/18.pdf", "Vodafone Idea Ltd", "FY18"),
    ("/Users/fti/personal_work/nair/pdfs/Vodafone Idea Ltd/23.pdf", "Vodafone Idea Ltd", "FY23"),
    ("/Users/fti/personal_work/nair/pdfs/Narayana Hrudayalaya Ltd/16.pdf", "Narayana Hrudayalaya Ltd", "FY16"),
    ("/Users/fti/personal_work/nair/pdfs/Narayana Hrudayalaya Ltd/19.pdf", "Narayana Hrudayalaya Ltd", "FY19"),
    ("/Users/fti/personal_work/nair/pdfs/Narayana Hrudayalaya Ltd/23.pdf", "Narayana Hrudayalaya Ltd", "FY23"),
]

def run_extraction(item):
    pdf_path, company, fy = item
    cmd = [
        "python3",
        "/Users/fti/personal_work/nair/POC3/extractor.py",
        "--pdf", pdf_path,
        "--company", company,
        "--year", fy,
        "--model", "gemini-3.1-flash-lite",
        "--concurrency", "4",
        "--force"
    ]
    print(f"[{time.strftime('%X')}] Starting POC3 extraction for {company} - {fy}...", flush=True)
    start_t = time.time()
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, check=True)
        elapsed = time.time() - start_t
        print(f"[{time.strftime('%X')}] ✅ Finished {company} - {fy} in {elapsed:.1f}s!", flush=True)
        return (company, fy, True, elapsed, res.stdout)
    except subprocess.CalledProcessError as e:
        elapsed = time.time() - start_t
        print(f"[{time.strftime('%X')}] ❌ Failed {company} - {fy} after {elapsed:.1f}s!\n{e.stderr}", flush=True)
        return (company, fy, False, elapsed, e.stderr)

def main():
    print("=== STARTING NEW DOMAINS EXTRACTION ===", flush=True)
    start_total = time.time()
    results = []
    # Using 2 concurrent workers to prevent API rate limits
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        futures = {executor.submit(run_extraction, run): run for run in RUNS}
        for future in concurrent.futures.as_completed(futures):
            results.append(future.result())
            
    print("\n=== EXECUTION SUMMARY ===", flush=True)
    for company, fy, success, elapsed, _ in sorted(results, key=lambda x: (x[0], x[1])):
        status = "✅ SUCCESS" if success else "❌ FAILED"
        print(f"{company} ({fy}): {status} ({elapsed:.1f}s)")
        
    total_elapsed = time.time() - start_total
    print(f"\nTotal Elapsed Time: {total_elapsed:.1f}s ({total_elapsed/60:.1f} mins)", flush=True)

if __name__ == "__main__":
    main()
