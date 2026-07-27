import json
import os
import threading
from pathlib import Path
from typing import Optional, List, Dict

class PipelineStateDB:
    def __init__(self, db_path: str = "pipeline_state.json"):
        self.db_path = Path(db_path)
        self.lock = threading.Lock()
        self._initialize_db()

    def _initialize_db(self):
        with self.lock:
            if not self.db_path.exists():
                with open(self.db_path, "w", encoding="utf-8") as f:
                    json.dump({"pdfs": []}, f, indent=2)

    def _read_db(self) -> dict:
        with open(self.db_path, "r", encoding="utf-8") as f:
            return json.load(f)

    def _write_db(self, data: dict):
        with open(self.db_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

    def add_pdf(self, company: str, fy: str, local_path: str):
        """Adds a PDF to the state tracker if it doesn't already exist."""
        with self.lock:
            data = self._read_db()
            # Check if exists
            for pdf in data["pdfs"]:
                if pdf["local_path"] == str(local_path):
                    return
            
            data["pdfs"].append({
                "company": company,
                "fy": fy,
                "local_path": str(local_path),
                "gemini_file_name": None,
                "status": "PENDING",
                "error_message": None,
                "retries": 0
            })
            self._write_db(data)

    def get_pdfs_by_status(self, status: str, limit: int = None) -> List[dict]:
        with self.lock:
            data = self._read_db()
            matches = [pdf for pdf in data["pdfs"] if pdf["status"] == status]
            if limit is not None:
                return matches[:limit]
            return matches

    def update_status(self, local_path: str, new_status: str, **kwargs):
        with self.lock:
            data = self._read_db()
            for pdf in data["pdfs"]:
                if pdf["local_path"] == str(local_path):
                    pdf["status"] = new_status
                    if "gemini_file_name" in kwargs:
                        pdf["gemini_file_name"] = kwargs["gemini_file_name"]
                    if "error_message" in kwargs:
                        pdf["error_message"] = kwargs["error_message"]
                    break
            self._write_db(data)

    def get_status_counts(self) -> Dict[str, int]:
        with self.lock:
            data = self._read_db()
            counts = {}
            for pdf in data["pdfs"]:
                st = pdf["status"]
                counts[st] = counts.get(st, 0) + 1
            return counts
