"""Local viewer for iterative edit runs.

Usage:
    python experiments/iterative_edit/viewer/server.py
"""

from __future__ import annotations

import json
import os
from collections import defaultdict
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse


ROOT = Path(__file__).resolve().parents[3]
VIEWER_DIR = Path(__file__).resolve().parent
RESULTS_DIR = ROOT / "results" / "iterative_edit"
HOST = os.getenv("HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", "8765"))


def coded_path_for_run(run_name: str) -> Path:
    if run_name.endswith(".jsonl"):
        return RESULTS_DIR / run_name.replace(".jsonl", "_changes_coded.json")
    return RESULTS_DIR / f"{run_name}_changes_coded.json"


def load_coded_records(run_name: str) -> dict[tuple[str, str, str, str, int], dict]:
    path = coded_path_for_run(run_name)
    if not path.exists():
        return {}

    with open(path, encoding="utf-8") as handle:
        items = json.load(handle)

    coded = {}
    for item in items:
        key = (
            item.get("condition_id") or "baseline",
            item.get("model_display") or "",
            item.get("document_id") or "",
            item.get("doc_type") or "",
            int(item.get("round_number") or 0),
        )
        coded[key] = {
            "summary": item.get("summary", ""),
            "dimensions": item.get("dimensions", {}),
            "coder_model": item.get("coder_model", ""),
        }
    return coded


def load_run_records(run_name: str) -> list[dict]:
    path = RESULTS_DIR / run_name
    if not path.exists():
        raise FileNotFoundError(run_name)

    records = []
    with open(path, encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            record = json.loads(line)
            records.append(record)
    return records


def summarize_run(run_name: str) -> dict:
    records = load_run_records(run_name)
    successful = [record for record in records if not record.get("error")]
    errors = [record for record in records if record.get("error")]
    return {
        "run_name": run_name,
        "record_count": len(records),
        "successful_count": len(successful),
        "error_count": len(errors),
        "models": sorted({record["model_display"] for record in records}),
        "documents": sorted({record["document_id"] for record in records}),
        "conditions": sorted({record.get("condition_name", "Baseline") for record in records}),
    }


def list_runs() -> list[dict]:
    runs = []
    for path in sorted(RESULTS_DIR.glob("run_*.jsonl"), reverse=True):
        runs.append(summarize_run(path.name))
    return runs


def changed_records(run_name: str) -> list[dict]:
    coded_records = load_coded_records(run_name)
    grouped: dict[tuple[str, str, str], list[dict]] = defaultdict(list)
    for record in load_run_records(run_name):
        key = (
            record["model_id"],
            record["document_id"],
            record.get("condition_id", "baseline"),
        )
        grouped[key].append(record)

    items = []
    for (_, _, _), chain in grouped.items():
        chain.sort(key=lambda record: record["round_number"])
        for record in chain:
            coding_key = (
                record.get("condition_id", "baseline"),
                record.get("model_display") or "",
                record.get("document_id") or "",
                record.get("doc_type") or "",
                int(record.get("round_number") or 0),
            )
            coding = coded_records.get(coding_key)
            if record.get("error"):
                previous_content = ""
            else:
                previous_record = next(
                    (
                        prior
                        for prior in reversed(chain)
                        if prior["round_number"] < record["round_number"] and not prior.get("error")
                    ),
                    None,
                )
                if previous_record is None:
                    previous_content = ""
                else:
                    previous_content = previous_record.get("new_content", "")

            items.append(
                {
                    "id": (
                        f"{run_name}:{record['model_id']}:{record['document_id']}:{record.get('condition_id', 'baseline')}:"
                        f"{record['round_number']}"
                    ),
                    "run_name": run_name,
                    "timestamp": record.get("timestamp"),
                    "condition_id": record.get("condition_id", "baseline"),
                    "condition_name": record.get("condition_name", "Baseline"),
                    "model_id": record.get("model_id"),
                    "model_display": record.get("model_display"),
                    "document_id": record.get("document_id"),
                    "document_provider": record.get("document_provider"),
                    "doc_type": record.get("doc_type"),
                    "round_number": record.get("round_number"),
                    "total_rounds": record.get("total_rounds"),
                    "change_description": record.get("change_description", ""),
                    "find_text": record.get("find_text", ""),
                    "replace_text": record.get("replace_text", ""),
                    "match_strategy": record.get("match_strategy", "exact"),
                    "retried": bool(record.get("retried")),
                    "no_change": bool(record.get("no_change")),
                    "error": record.get("error"),
                    "input_tokens": record.get("input_tokens", 0),
                    "output_tokens": record.get("output_tokens", 0),
                    "elapsed_ms": record.get("elapsed_ms", 0),
                    "previous_content": previous_content,
                    "new_content": record.get("new_content", ""),
                    "coding": coding,
                }
            )

    items.sort(
        key=lambda record: (
            record["condition_name"] or "",
            record["model_display"] or "",
            record["document_id"] or "",
            record["round_number"] or 0,
        )
    )
    return items


class ViewerHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        parsed = urlparse(self.path)

        if parsed.path == "/healthz":
            self.send_json({"ok": True})
            return
        if parsed.path == "/":
            self.serve_file("index.html", "text/html; charset=utf-8")
            return
        if parsed.path == "/app.js":
            self.serve_file("app.js", "application/javascript; charset=utf-8")
            return
        if parsed.path == "/styles.css":
            self.serve_file("styles.css", "text/css; charset=utf-8")
            return
        if parsed.path == "/api/runs":
            self.send_json(list_runs())
            return
        if parsed.path == "/api/run":
            params = parse_qs(parsed.query)
            run_name = params.get("name", [""])[0]
            if not run_name:
                self.send_error(HTTPStatus.BAD_REQUEST, "Missing run name")
                return
            try:
                payload = {
                    "run_name": run_name,
                    "records": changed_records(run_name),
                }
            except FileNotFoundError:
                self.send_error(HTTPStatus.NOT_FOUND, "Run not found")
                return
            self.send_json(payload)
            return

        self.send_error(HTTPStatus.NOT_FOUND, "Not found")

    def log_message(self, format: str, *args) -> None:
        return

    def serve_file(self, name: str, content_type: str) -> None:
        path = VIEWER_DIR / name
        if not path.exists():
            self.send_error(HTTPStatus.NOT_FOUND, "File not found")
            return

        data = path.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def send_json(self, payload: dict | list) -> None:
        data = json.dumps(payload).encode("utf-8")
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


def main() -> None:
    server = ThreadingHTTPServer((HOST, PORT), ViewerHandler)
    print(f"Viewer running at http://{HOST}:{PORT}")
    server.serve_forever()


if __name__ == "__main__":
    main()
