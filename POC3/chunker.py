import fitz
from pathlib import Path
from dataclasses import dataclass

@dataclass
class PDFChunk:
    path: Path
    start_page: int
    end_page: int
    
def get_pdf_page_count(pdf_path: Path | str) -> int:
    try:
        doc = fitz.open(pdf_path)
        pages = len(doc)
        doc.close()
        return pages
    except Exception:
        return 0

def chunk_pdf(pdf_path: Path | str, max_pages: int = 300, overlap: int = 10, output_dir: Path | str | None = None) -> list[PDFChunk]:
    """
    Slices a large PDF into overlapping chunks.
    """
    pdf_path = Path(pdf_path)
    if output_dir is None:
        output_dir = pdf_path.parent / ".chunks"
    else:
        output_dir = Path(output_dir)
        
    output_dir.mkdir(parents=True, exist_ok=True)
    
    doc = fitz.open(pdf_path)
    total_pages = len(doc)
    
    if total_pages <= max_pages:
        doc.close()
        return [PDFChunk(path=pdf_path, start_page=0, end_page=total_pages-1)]
        
    chunks = []
    start = 0
    
    while start < total_pages:
        end = min(start + max_pages, total_pages) - 1
        
        # Don't create a tiny chunk at the end if we can help it, but it's fine.
        chunk_name = f"{pdf_path.stem}_chunk_{start+1}_{end+1}{pdf_path.suffix}"
        chunk_path = output_dir / chunk_name
        
        # Only write if it doesn't already exist to save time on reruns
        if not chunk_path.exists():
            new_doc = fitz.open()
            new_doc.insert_pdf(doc, from_page=start, to_page=end)
            new_doc.save(chunk_path, garbage=4, deflate=True)
            new_doc.close()
            
        chunks.append(PDFChunk(path=chunk_path, start_page=start, end_page=end))
        
        # Move start pointer forward, accounting for overlap
        if end == total_pages - 1:
            break
            
        start = end + 1 - overlap
        
    doc.close()
    return chunks
