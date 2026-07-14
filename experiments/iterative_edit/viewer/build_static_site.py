"""Rebuild the data bundle for the GitHub Pages site.

The site source (HTML/JS/CSS) lives directly in docs/, which GitHub Pages
serves; this script only regenerates docs/data/site.json[.gz] from the run
results and the judge/beneficiary coding.

Usage:
    python experiments/iterative_edit/viewer/build_static_site.py
"""

from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
RESULTS_DIR = ROOT / "results" / "iterative_edit"
DOCS_DIR = ROOT / "docs"
DATA_DIR = DOCS_DIR / "data"
ACTIVE_DIMENSIONS = {"authority", "user_stance", "telos"}

# Runs whose infrastructure and round count we trust for cross-run comparison.
# Anything not listed here is treated as exploratory/test and only shown when
# the "Include exploratory runs" toggle is on in the viewer.
RELIABLE_RUNS = {
    "run_20260403_014905.jsonl",  # small-model ablation sweep, 20 rounds
    "run_20260424_165115.jsonl",  # small-model cross-edit, 20 rounds
    "run_20260429_175345.jsonl",  # capable-model baseline, 20 rounds
    "run_20260507_212254.jsonl",  # capable-model ablation sweep, 20 rounds
    "run_20260513_193319.jsonl",  # capable-model cross-edit, 20 rounds
    "run_20260516_210913.jsonl",  # frontier ablations (Opus 4.7 + GPT-5.5 medium), 20 rounds
    "run_20260518_171402.jsonl",  # frontier cross-edit (Opus 4.7 + GPT-5.5 medium), 20 rounds
}


# Single combined judge/beneficiary coding file (judge / patienthood /
# conflicts) covering every reliable run, produced by qualitative_code.py.
CODED_PATH = RESULTS_DIR / "judge_beneficiary_coded_gemma.json"


def load_jsonl_records(path: Path) -> list[dict]:
    records = []
    with open(path, encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            records.append(json.loads(line))
    return records


_coded_cache: dict[tuple[str, str, str, str, str, int], dict] | None = None


def load_judge_beneficiary_coded() -> dict[tuple[str, str, str, str, str, int], dict]:
    """Load the combined judge/beneficiary coding file, keyed by
    (run_stem, condition_id, model_display, document_id, doc_type, round)."""
    global _coded_cache
    if _coded_cache is not None:
        return _coded_cache
    coded: dict[tuple[str, str, str, str, str, int], dict] = {}
    if CODED_PATH.exists():
        with open(CODED_PATH, encoding="utf-8") as handle:
            items = json.load(handle)
        for item in items:
            coding = item.get("coding") or {}
            if coding.get("error"):
                continue
            key = (
                item.get("source_run") or "",
                item.get("condition_id") or "baseline",
                item.get("model_display") or "",
                item.get("document_id") or "",
                item.get("doc_type") or "",
                int(item.get("round_number") or 0),
            )
            coded[key] = {
                "summary": coding.get("summary", ""),
                "judge": coding.get("judge"),
                "patienthood": coding.get("patienthood"),
                "conflicts": coding.get("conflicts") or [],
                "coder_model": item.get("coder_model", ""),
            }
    _coded_cache = coded
    return coded


def summarize_run(records: list[dict], run_name: str) -> dict:
    successful = [record for record in records if not record.get("error")]
    errors = [record for record in records if record.get("error")]
    return {
        "run_name": run_name,
        "is_reliable": run_name in RELIABLE_RUNS,
        "record_count": len(records),
        "successful_count": len(successful),
        "error_count": len(errors),
        "models": sorted({record["model_display"] for record in records}),
        "documents": sorted({record["document_id"] for record in records}),
        "conditions": sorted({record.get("condition_name", "Baseline") for record in records}),
        "total_rounds": max(
            (int(record.get("total_rounds") or 0) for record in records),
            default=0,
        ),
    }


def changed_records(run_name: str, records: list[dict]) -> list[dict]:
    coded_records = load_judge_beneficiary_coded()
    run_stem = run_name.replace(".jsonl", "")
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
                run_stem,
                record.get("condition_id", "baseline"),
                record.get("model_display") or "",
                record.get("document_id") or "",
                record.get("doc_type") or "",
                int(record.get("round_number") or 0),
            )
            coding = coded_records.get(coding_key)

            # previous_content / new_content (the running document after each
            # round) used to be embedded here for a diff view that was later
            # dropped. They dominate the bundle size (~95% of the payload)
            # and the viewer no longer reads them, so they are intentionally
            # omitted. find_text / replace_text are kept so the record cards
            # can still show the local before/after.
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
