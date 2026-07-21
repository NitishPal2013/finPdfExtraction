#!/usr/bin/env python3
"""
Batch Directory Runner: Scans a PDF directory for company subfolders, identifies PDF files,
and runs the extraction pipeline concurrently.
"""
import os
import sys
import glob
import time
import argparse
import subprocess
import concurrent.futures
from pathlib import Path

def parse_args():
    parser = argparse.ArgumentParser(description="Process all company PDFs in a directory structure.")
    parser.add_argument("--dir", required=True, help="Base directory containing company subfolders (e.g. ./pdfs)")
    parser.add_argument("--workers", type=int, default=4, help="Number of concurrent company/PDF workers (default: 4)")
    parser.add_argument("--concurrency", type=int, default=4, help="Semaphore limit inside extractor (default: 4)")
    parser.add_argument("--out-suffix", default="_POC3", help="Output file suffix (default: _POC3)")
    parser.add_argument("--model", default="gemini-3.1-flash-lite", help="Gemini model name")
    parser.add_argument("--force", action="store_true", help="Overwrite existing output sheets")
    return parser.parse_args()

def process_single_file(args_tuple):
    pdf_path, company_name, fy_year, workers_args = args_tuple
    cmd = [
        sys.executable,
        str(Path(__file__).parent / "extractor.py"),
        "--pdf", str(pdf_path),
        "--company", company_name,
        "--year", fy_year,
        "--model", workers_args.model,
        "--concurrency", str(workers_args.concurrency),
        "--out-suffix", workers_args.out_suffix
    ]
    if workers_args.force:
        cmd.append("--force")

    t_start = time.time()
    print(f"[{time.strftime('%X')}] 🚀 Launching extraction: {company_name} - {fy_year}...", flush=True)
    try:
        # We allow printing directly to console so logs interleave in real-time
        res = subprocess.run(cmd, check=True)
        elapsed = time.time() - t_start
        print(f"[{time.strftime('%X')}] ✅ SUCCESS: {company_name} - {fy_year} in {elapsed:.1f}s", flush=True)
        return (company_name, fy_year, True, elapsed)
    except subprocess.CalledProcessError as e:
        elapsed = time.time() - t_start
        print(f"[{time.strftime('%X')}] ❌ FAILED: {company_name} - {fy_year} after {elapsed:.1f}s", flush=True)
        return (company_name, fy_year, False, elapsed)

def main():
    args = parse_args()
    base_path = Path(args.dir).resolve()
    
    if not base_path.exists() or not base_path.is_dir():
        print(f"Error: Directory does not exist: {base_path}")
        sys.exit(1)

    print(f"=== BATCH EXTRACTION INITIALIZED ===")
    print(f"Directory:    {base_path}")
    print(f"Max Workers:  {args.workers} (Parallel PDFs)")
    print(f"Concurrency:  {args.concurrency} (Parallel queries per PDF)")
    print(f"Output Suffix: {args.out_suffix}")
    print(f"====================================\n")

    # Find all PDFs in company_name/year.pdf structure
    # We accept: pdfs/Company Name/13.pdf, 23.pdf, etc.
    pdf_tasks = []
    
    # Scan subdirectories
    for company_dir in sorted(base_path.iterdir()):
        if not company_dir.is_dir():
            continue
        
        company_name = company_dir.name
        # Find PDF files matching [two-digit year].pdf
        for pdf_p in company_dir.glob("*.pdf"):
            stem = pdf_p.stem
            # We check if filename represents a year (e.g. 13, 23, 16, 2013, 2023)
            if stem.isdigit() and len(stem) in (2, 4):
                fy_year = f"FY{stem[-2:]}"
                pdf_tasks.append((pdf_p, company_name, fy_year, args))

    if not pdf_tasks:
        print("No valid PDFs found matching 'Company_Name/[year].pdf' structure.")
        sys.exit(0)

    print(f"Found {len(pdf_tasks)} PDFs to process.\n")
    start_time = time.time()
    results = []

    # Run the tasks concurrently using ThreadPoolExecutor
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = {executor.submit(process_single_file, task): task for task in pdf_tasks}
        for future in concurrent.futures.as_completed(futures):
            results.append(future.result())

    print("\n" + "=" * 50)
    print("BATCH RUN COMPLETE SUMMARY:")
    print("=" * 50)
    success_cnt = 0
    for comp, fy, success, duration in sorted(results, key=lambda x: (x[0], x[1])):
        status = "✅ SUCCESS" if success else "❌ FAILED"
        if success:
            success_cnt += 1
        print(f"  * {comp} ({fy}): {status} ({duration:.1f}s)")
    
    total_time = time.time() - start_time
    print(f"\nTotal Elapsed Time: {total_time:.1f}s ({total_time/60:.1f} mins)")
    print(f"Success Rate: {success_cnt}/{len(pdf_tasks)} ({success_cnt/len(pdf_tasks)*100:.1f}%)")

if __name__ == "__main__":
    main()
