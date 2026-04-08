"""Export simplified JSON views of iterative edit runs.

Usage:
    python experiments/iterative_edit/export_changes.py \
        results/iterative_edit/run_20260320_173238.jsonl
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Sanitization: strip chain-of-thought, duplicate edits, and conversational
# follow-up that some models appended after the replacement text.
# This cleans up contaminated data from existing runs.
# ---------------------------------------------------------------------------

_THINKING_TAG_RE = re.compile(r"<thinking>.*?</thinking>\s*", re.DOTALL)
_ORPHAN_THINKING_CLOSE_RE = re.compile(r"\s*</thinking>\s*")
_SECOND_EDIT_RE = re.compile(r"\n*---CHANGE DESCRIPTION---.*", re.DOTALL)
_TRAILING_COT_RE = re.compile(
    r"\n---\n\n"
    r"(?="
    r"(?:Hmm|Actually|Wait|Let me|I think|---CHANGE DESCRIPTION)"
    r")",
    re.IGNORECASE,
)
_FREEFORM_COT_RE = re.compile(
    r"\n{2,}"
    r"(?:Wait, let me reconsider|Hmm, (?:I'm noticing|actually|let me)|"
    r"Actually, let me (?:reconsider|try)|"
    r"Let me (?:reconsider|refine|check if|think about what))"
    r".*",
    re.DOTALL | re.IGNORECASE,
)
_TRAILING_CONVO_RE = re.compile(
    r"\n{2,}"
    r"(?:Would you like|Shall I|Let me know if|Do you want me to|Here are some"
    r"|Note:|I can also|Is there anything)"
    r".*",
    re.DOTALL | re.IGNORECASE,
)


def sanitize_replace_text(text: str) -> str:
    """Remove model chain-of-thought and conversational noise from replace_text."""
    text = _THINKING_TAG_RE.sub("", text)
    text = _ORPHAN_THINKING_CLOSE_RE.sub("", text)
    text = _SECOND_EDIT_RE.split(text, maxsplit=1)[0]
    text = _TRAILING_COT_RE.split(text, maxsplit=1)[0]
    text = _FREEFORM_COT_RE.split(text, maxsplit=1)[0]
    text = _TRAILING_CONVO_RE.split(text, maxsplit=1)[0]
    return text.strip()


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
            raw_replace = "" if record.get("no_change") else record.get("replace_text", "")
            records.append(
                {
                    "condition_id": record.get("condition_id", "baseline"),
                    "condition_name": record.get("condition_name", "Baseline"),
                    "model_display": record.get("model_display"),
                    "document_id": record.get("document_id"),
                    "doc_type": record.get("doc_type"),
                    "round_number": record.get("round_number"),
                    "no_change": bool(record.get("no_change")),
                    "error": record.get("error"),
                    "original_text": "" if record.get("no_change") else record.get("find_text", ""),
                    "changed_text": sanitize_replace_text(raw_replace),
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
