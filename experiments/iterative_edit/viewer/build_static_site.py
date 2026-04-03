"""Build a static GitHub Pages version of the iterative edit viewer.

Usage:
    python experiments/iterative_edit/viewer/build_static_site.py
"""

from __future__ import annotations

import json
import shutil
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
VIEWER_DIR = Path(__file__).resolve().parent
RESULTS_DIR = ROOT / "results" / "iterative_edit"
DOCS_DIR = ROOT / "docs"
DATA_DIR = DOCS_DIR / "data"
ACTIVE_DIMENSIONS = {"authority", "user_stance", "telos"}


def coded_path_for_run(run_name: str) -> Path:
    # Prefer the explicitly versioned coded file if available
    v2_path = RESULTS_DIR / run_name.replace(".jsonl", "_changes_coded_v2.json")
    if v2_path.exists():
        return v2_path
    return RESULTS_DIR / run_name.replace(".jsonl", "_changes_coded.json")


def load_jsonl_records(path: Path) -> list[dict]:
    records = []
    with open(path, encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            records.append(json.loads(line))
    return records


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
            "dimensions": {
                name: value
                for name, value in (item.get("dimensions", {}) or {}).items()
                if name in ACTIVE_DIMENSIONS
            },
            "coder_model": item.get("coder_model", ""),
        }
    return coded


def summarize_run(records: list[dict], run_name: str) -> dict:
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


def changed_records(run_name: str, records: list[dict]) -> list[dict]:
    coded_records = load_coded_records(run_name)
    grouped: dict[tuple[str, str, str], list[dict]] = defaultdict(list)
    for record in records:
        key = (
            record["model_id"],
            record["document_id"],
            record.get("condition_id", "baseline"),
        )
        grouped[key].append(record)

    items = []
    for chain in grouped.values():
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
                previous_content = previous_record.get("new_content", "") if previous_record else ""

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


def build_bundle() -> dict:
    runs = []
    for path in sorted(RESULTS_DIR.glob("run_*.jsonl"), reverse=True):
        raw_records = load_jsonl_records(path)
        summary = summarize_run(raw_records, path.name)
        summary["records"] = changed_records(path.name, raw_records)
        runs.append(summary)

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "runs": runs,
    }


def build_static_site() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    shutil.copy2(VIEWER_DIR / "index.html", DOCS_DIR / "index.html")
    shutil.copy2(VIEWER_DIR / "app.js", DOCS_DIR / "app.js")
    shutil.copy2(VIEWER_DIR / "styles.css", DOCS_DIR / "styles.css")
    (DOCS_DIR / ".nojekyll").write_text("", encoding="utf-8")

    bundle = build_bundle()
    with open(DATA_DIR / "site.json", "w", encoding="utf-8") as handle:
        json.dump(bundle, handle, indent=2, ensure_ascii=False)
        handle.write("\n")

    import gzip as _gzip
    json_bytes = json.dumps(bundle, ensure_ascii=False).encode("utf-8")
    with _gzip.open(DATA_DIR / "site.json.gz", "wb") as gz:
        gz.write(json_bytes)


def main() -> None:
    build_static_site()
    print(DOCS_DIR)


if __name__ == "__main__":
    main()
