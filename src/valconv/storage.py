"""JSONL append-only storage for crash safety and resumability."""

import json
from pathlib import Path
from typing import TypeVar

from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)


def append_record(path: Path, record: BaseModel) -> None:
    """Append a single record to a JSONL file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(record.model_dump_json() + "\n")


def load_records(path: Path, model_class: type[T]) -> list[T]:
    """Load all records from a JSONL file."""
    if not path.exists():
        return []
    records = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(model_class.model_validate_json(line))
    return records


def get_completed_rounds(
    path: Path,
    model_id: str,
    document_id: str,
    condition_id: str = "baseline",
) -> set[int]:
    """Get set of completed round numbers for a model+document+condition chain."""
    completed = set()
    if not path.exists():
        return completed
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
                if (
                    record.get("model_id") == model_id
                    and record.get("document_id") == document_id
                    and record.get("condition_id", "baseline") == condition_id
                    and record.get("error") is None
                ):
                    completed.add(record["round_number"])
            except (json.JSONDecodeError, KeyError):
                pass
    return completed
