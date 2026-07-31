import json
import time
import os
import threading
from pathlib import Path

class LiveTracker:
    def __init__(self):
        self.lock = threading.Lock()
        self.current_pdf = None
        self.current_status = None
        self.current_details = None
        
        # Start the background heartbeat pinger
        self.pinger_thread = threading.Thread(target=self._pinger, daemon=True)
        self.pinger_thread.start()
        
    def _pinger(self):
        while True:
            time.sleep(10)  # Ping every 10 seconds to prevent STALLED status
            with self.lock:
                if self.current_pdf and self.current_status not in ("DONE", "ERROR"):
                    self._write_file(self.current_pdf, self.current_status, self.current_details)

    def _get_status_path(self, pdf_path: Path) -> Path:
        return pdf_path.parent / f"{pdf_path.name}.status"

    def _write_file(self, pdf_path: Path, status: str, details: str):
        status_file = self._get_status_path(pdf_path)
        data = {
            "status": status,
            "details": details,
            "last_updated": time.time(),
            "pid": os.getpid()
        }
        try:
            status_file.write_text(json.dumps(data, indent=2), encoding="utf-8")
        except Exception:
            pass

    def update(self, pdf_path: str | Path, status: str, details: str = ""):
        path = Path(pdf_path)
        with self.lock:
            self.current_pdf = path
            self.current_status = status
            self.current_details = details
            self._write_file(path, status, details)
            
    def set_batch(self, pdf_paths: list[str | Path]):
        """Initializes the batch with QUEUED status"""
        for p in pdf_paths:
            path = Path(p)
            status_file = self._get_status_path(path)
            if not status_file.exists():
                with self.lock:
                    self._write_file(path, "QUEUED", "")

# Global singleton
tracker = LiveTracker()
