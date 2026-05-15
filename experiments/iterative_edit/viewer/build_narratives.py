"""Build docs/data/narratives.json from pattern-coded data.

For each pattern in pattern_code.py, aggregates present/total counts per
(condition x model) across every *_pattern_coded.json file in
results/iterative_edit/, and stores all present examples (capped per
pattern x condition x model so the bundle stays small).

Usage:
    python experiments/iterative_edit/viewer/build_narratives.py
"""

from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
RESULTS_DIR = ROOT / "results" / "iterative_edit"
DOCS_DATA_DIR = ROOT / "docs" / "data"

# Cap stored examples per (pattern, condition, model) cell so the bundle
# stays small. The viewer shuffles within the filtered pool, so a few dozen
# is plenty to give the impression of "typical examples for this category."
EXAMPLES_PER_CELL = 25

# Truncate long source/replacement text so individual examples don't blow up
# the bundle size. Most edits are well under this, and the records viewer is
# the right place to read the full text if needed.
TEXT_CHAR_CAP = 1800

# Import PATTERNS so we know which pattern ids to emit even if absent in data.
sys.path.insert(0, str(ROOT / "experiments" / "iterative_edit"))
from pattern_code import PATTERNS  # type: ignore


def load_changes_for_run(run_stem: str) -> dict[tuple, dict]:
    """Map (condition_id, model_display, document_id, doc_type, round) -> change record."""
    changes_path = RESULTS_DIR / f"{run_stem}_changes.json"
    if not changes_path.exists():
        return {}
    with open(changes_path, encoding="utf-8") as handle:
        items = json.load(handle)
    result = {}
    for item in items:
        key = (
            item.get("condition_id", "baseline"),
            item.get("model_display") or "",
            item.get("document_id") or "",
            item.get("doc_type") or "",
            int(item.get("round_number") or 0),
        )
        result[key] = item
    return result


def pattern_coded_files() -> list[Path]:
    return sorted(RESULTS_DIR.glob("run_*_pattern_coded.json"), reverse=True)


def _truncate(text: str | None) -> str:
    if not text:
        return ""
    if len(text) <= TEXT_CHAR_CAP:
        return text
    return text[:TEXT_CHAR_CAP] + "\n\n[...truncated for size; see full record in main viewer]"


def build() -> dict:
    pattern_ids = [p["id"] for p in PATTERNS]
    # stats[pattern_id][condition_id][model_display] = {present, total}
    stats: dict[str, dict[str, dict[str, dict]]] = {
        pid: defaultdict(lambda: defaultdict(lambda: {"present": 0, "total": 0}))
        for pid in pattern_ids
    }
    # examples_by_cell[(pattern_id, condition_id, model_display)] = [example, ...]
    examples_by_cell: dict[tuple[str, str, str], list[dict]] = defaultdict(list)

    confidence_rank = {"high": 3, "medium": 2, "low": 1, "error": 0}

    for pc_path in pattern_coded_files():
        run_stem = pc_path.name.replace("_pattern_coded.json", "")
        changes = load_changes_for_run(run_stem)

        with open(pc_path, encoding="utf-8") as handle:
            coded = json.load(handle)

        for item in coded:
            condition = item.get("condition_id", "baseline")
            model = item.get("model_display") or ""
            key = (
                condition,
                model,
                item.get("document_id") or "",
                item.get("doc_type") or "",
                int(item.get("round_number") or 0),
            )
            change = changes.get(key, {})
            for pid, pdata in (item.get("patterns") or {}).items():
                if pid not in stats:
                    stats[pid] = defaultdict(lambda: defaultdict(lambda: {"present": 0, "total": 0}))
                stats[pid][condition][model]["total"] += 1
                if not pdata.get("present"):
                    continue
                stats[pid][condition][model]["present"] += 1

                cell = (pid, condition, model)
                examples_by_cell[cell].append(
                    {
                        "id": f"{run_stem}:{model}:{item.get('document_id')}:{condition}:{item.get('round_number')}",
                        "round": item.get("round_number"),
                        "condition_id": condition,
                        "condition_name": item.get("condition_name", condition),
                        "evidence": pdata.get("evidence", ""),
                        "original_text": _truncate(change.get("original_text", "")),
                        "changed_text": _truncate(change.get("changed_text", "")),
                        "model_display": model,
                        "document_id": item.get("document_id"),
                        "confidence": pdata.get("confidence", "medium"),
                        "confidence_rank": confidence_rank.get(pdata.get("confidence", "medium"), 1),
                    }
                )

    # For each (pattern, condition, model) cell, keep at most EXAMPLES_PER_CELL
    # examples, preferring higher-confidence ones first, then later rounds.
    stories: dict[str, list[dict]] = {pid: [] for pid in pattern_ids}
    for (pid, condition, model), exs in examples_by_cell.items():
        exs.sort(key=lambda e: (e["confidence_rank"], e["round"] or 0), reverse=True)
        capped = exs[:EXAMPLES_PER_CELL]
        # Strip the helper rank field before emitting.
        for ex in capped:
            ex.pop("confidence_rank", None)
        if pid in stories:
            stories[pid].extend(capped)

    # Convert nested defaultdicts to plain dicts for JSON serialization.
    stats_out: dict[str, dict] = {}
    for pid in pattern_ids:
        cond_map = {}
        for cond, model_map in stats.get(pid, {}).items():
            cond_map[cond] = {model: dict(c) for model, c in model_map.items()}
        stats_out[pid] = cond_map

    return {"stats": stats_out, "stories": stories}


def main() -> None:
    DOCS_DATA_DIR.mkdir(parents=True, exist_ok=True)
    bundle = build()
    with open(DOCS_DATA_DIR / "narratives.json", "w", encoding="utf-8") as handle:
        json.dump(bundle, handle, indent=2, ensure_ascii=False)
        handle.write("\n")
    print(DOCS_DATA_DIR / "narratives.json")


if __name__ == "__main__":
    main()
