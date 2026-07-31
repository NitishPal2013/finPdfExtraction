import time
import json
import argparse
from pathlib import Path
from rich.live import Live
from rich.table import Table
from rich.console import Console

console = Console()

def get_table(directory: Path) -> Table:
    table = Table(title=f"🚀 POC3 Live Extraction Dashboard: {directory.name}", title_justify="left", show_lines=True)
    table.add_column("PDF", style="cyan", no_wrap=True)
    table.add_column("Status", justify="center", style="bold")
    table.add_column("Details", style="dim")

    if not directory.exists():
        table.add_row("Directory not found", "-", "-")
        return table

    pdfs = sorted([p for p in directory.glob("*.pdf") if "_gs_compressed" not in p.name and not p.name.endswith("_audit_pages.pdf")])
    
    if not pdfs:
        table.add_row("No PDFs found...", "-", "-")
        return table

    current_time = time.time()

    for pdf in pdfs:
        xlsx_path = pdf.parent / f"{pdf.stem}_POC3.xlsx"
        status_path = pdf.parent / f"{pdf.name}.status"
        
        st = "UNKNOWN"
        det = ""

        if xlsx_path.exists():
            st = "DONE"
            det = "Completed & Cleaned up"
        elif status_path.exists():
            try:
                data = json.loads(status_path.read_text(encoding="utf-8"))
                st = data.get("status", "UNKNOWN")
                det = data.get("details", "")
                
                # Heartbeat check
                last_updated = data.get("last_updated", 0)
                if st not in ("DONE", "ERROR", "QUEUED") and (current_time - last_updated) > 30:
                    st = "STALLED"
                    det = f"Worker died? (No heartbeat in {int(current_time - last_updated)}s)"
            except Exception:
                st = "ERROR"
                det = "Could not read status file"
        else:
            st = "QUEUED"

        color = "white"
        if st == "QUEUED": color = "dim white"
        elif st == "PREPROCESSING": color = "yellow"
        elif st == "UPLOADING": color = "blue"
        elif st == "HARVESTING": color = "magenta"
        elif st == "FINALIZING": color = "cyan"
        elif st == "DONE": color = "green"
        elif st == "ERROR": color = "red"
        elif st == "STALLED": color = "bold red"

        table.add_row(pdf.name, f"[{color}]{st}[/{color}]", det)

    return table

def main():
    parser = argparse.ArgumentParser(description="Live Dashboard for POC3 Extractions")
    parser.add_argument("--dir", required=True, help="Directory containing the PDFs being processed")
    args = parser.parse_args()
    
    target_dir = Path(args.dir).resolve()

    with Live(get_table(target_dir), refresh_per_second=2, console=console) as live:
        try:
            while True:
                time.sleep(0.5)
                live.update(get_table(target_dir))
        except KeyboardInterrupt:
            pass

if __name__ == "__main__":
    main()
