import subprocess
import shutil
import math
import fitz
from pathlib import Path
from typing import List

from POC3.live_tracker import tracker

def compress_pdf(input_path: str | Path, output_path: str | Path) -> str:
    """
    Compresses a PDF using Ghostscript with screen quality settings.
    This strips hidden layers, embedded fonts, and heavily downscales images
    to prevent file size bloat from triggering Context Cache limits.
    """
    input_path = Path(input_path)
    output_path = Path(output_path)
    
    if not input_path.exists():
        raise FileNotFoundError(f"Cannot compress, file not found: {input_path}")
        
    if not shutil.which("gs"):
        print("[WARNING] Ghostscript ('gs') not found on system. Skipping compression.")
        return str(input_path)
        
    print(f"[preprocessor] Compressing PDF {input_path.name}...")
    original_size = input_path.stat().st_size / (1024 * 1024)
    
    cmd = [
        "gs",
        "-sDEVICE=pdfwrite",
        "-dCompatibilityLevel=1.4",
        "-dPDFSETTINGS=/screen",
        "-dNOPAUSE",
        "-dQUIET",
        "-dBATCH",
        f"-sOutputFile={str(output_path)}",
        str(input_path)
    ]
    
    try:
        subprocess.run(cmd, check=True, capture_output=True)
    except subprocess.CalledProcessError as e:
        print(f"[ERROR] Ghostscript compression failed: {e.stderr.decode('utf-8', errors='ignore')}")
        return str(input_path)
        
    new_size = output_path.stat().st_size / (1024 * 1024)
    print(f"[preprocessor] Compressed {input_path.name}: {original_size:.1f} MB -> {new_size:.1f} MB")
    
    return str(output_path)

def chunk_pdf(input_path: str | Path, max_chunk_size_mb: float = 45.0) -> List[str]:
    """
    Dynamically splits a PDF into the minimum number of chunks such that
    no single chunk exceeds max_chunk_size_mb. Measures exact byte sizes in memory.
    """
    input_path = Path(input_path)
    size_mb = input_path.stat().st_size / (1024 * 1024)
    
    if size_mb <= max_chunk_size_mb:
        return [str(input_path)]
        
    print(f"[preprocessor] File size {size_mb:.1f}MB exceeds {max_chunk_size_mb}MB. Dynamically calculating minimum chunks...")
    
    doc = fitz.open(str(input_path))
    total_pages = doc.page_count
    
    chunk_paths = []
    start_page = 0
    chunk_idx = 1
    
    while start_page < total_pages:
        current_doc = fitz.open()
        end_page = start_page
        
        while end_page < total_pages:
            current_doc.insert_pdf(doc, from_page=end_page, to_page=end_page)
            # Measure exact byte weight in memory
            current_size_mb = len(current_doc.tobytes(garbage=4, deflate=True)) / (1024 * 1024)
            
            if current_size_mb > max_chunk_size_mb:
                if end_page > start_page:
                    # This page pushed us over the limit, and we already have at least 1 page in the chunk.
                    # Remove the page we just added so the chunk stays under the limit.
                    current_doc.delete_page(-1)
                    break
                else:
                    # A single page itself is larger than the limit! Force rasterize it.
                    print(f"[preprocessor] WARNING: Single page {end_page+1} is {current_size_mb:.1f}MB (>{max_chunk_size_mb}MB). Force-rasterizing...")
                    page = doc.load_page(end_page)
                    pix = page.get_pixmap(dpi=72)
                    img_bytes = pix.tobytes("jpeg")
                    img_doc = fitz.open()
                    img_page = img_doc.new_page(width=page.rect.width, height=page.rect.height)
                    img_page.insert_image(img_page.rect, stream=img_bytes)
                    current_doc.close()
                    current_doc = img_doc
                    break
                    
                
            end_page += 1
            
        chunk_path = input_path.parent / f"{input_path.stem}_chunk{chunk_idx}{input_path.suffix}"
        current_doc.save(str(chunk_path), garbage=4, deflate=True)
        current_doc.close()
        
        chunk_size = chunk_path.stat().st_size / (1024 * 1024)
        print(f"[preprocessor] Saved {chunk_path.name}: Pages {start_page+1}-{end_page} ({chunk_size:.1f} MB)")
        
        chunk_paths.append(str(chunk_path))
        chunk_idx += 1
        
        # If a single page is larger than max_chunk_size_mb, we are forced to advance anyway
        # (the loop above breaks immediately, but end_page isn't incremented)
        start_page = end_page if end_page > start_page else start_page + 1
            
    doc.close()
    return chunk_paths

def preprocess_if_needed(input_path: str | Path, size_threshold_mb: float = 50.0) -> List[str]:
    """
    Checks if a PDF exceeds the size threshold. If so, compresses it.
    If the compressed file is STILL too large, it dynamically chunks it.
    Returns a list of paths to the files to use (1 or more chunks).
    """
    input_path = Path(input_path)
    if not input_path.exists():
        return [str(input_path)]
        
    size_mb = input_path.stat().st_size / (1024 * 1024)
    target_path = input_path
    
    if size_mb > size_threshold_mb:
        tracker.update(input_path.name, "PREPROCESSING", f"Compressing & Chunking ({size_mb:.1f} MB)")
        output_path = input_path.parent / f"{input_path.stem}_gs_compressed{input_path.suffix}"
        if not output_path.exists():
            compressed_str = compress_pdf(input_path, output_path)
            target_path = Path(compressed_str)
        else:
            print(f"[preprocessor] Found existing compressed file: {output_path.name}")
            target_path = output_path
            
    return chunk_pdf(target_path, max_chunk_size_mb=45.0)
