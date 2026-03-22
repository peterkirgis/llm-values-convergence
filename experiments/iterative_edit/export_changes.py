"""Export simplified JSON views of iterative edit runs.

Usage:
    python experiments/iterative_edit/export_changes.py \
        results/iterative_edit/run_20260320_173238.jsonl
"""

from __future__ import annotations

import json
import sys
from pathlib import Path


def build_output_path(input_path: Path) -> Path:
    stem = input_path.stem
    return input_path.with_name(f"{stem}_changes.json")


def export_changes(input_path: Path) -> Path:
    records = []
    with open(input_path, encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            record = json.loads(line)
            records.append(
                {
                    "model_display": record.get("model_display"),
                    "document_id": record.get("document_id"),
                    "doc_type": record.get("doc_type"),
                    "round_number": record.get("round_number"),
                    "error": record.get("error"),
                    "original_text": record.get("find_text", ""),
                    "changed_text": record.get("replace_text", ""),
                }
            )

    output_path = build_output_path(input_path)
    with open(output_path, "w", encoding="utf-8") as handle:
        json.dump(records, handle, indent=2, ensure_ascii=False)
        handle.write("\n")

    return output_path


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit(
            "Usage: python experiments/iterative_edit/export_changes.py "
            "results/iterative_edit/run_YYYYMMDD_HHMMSS.jsonl"
        )

    input_path = Path(sys.argv[1])
    output_path = export_changes(input_path)
    print(output_path)


if __name__ == "__main__":
    main()
