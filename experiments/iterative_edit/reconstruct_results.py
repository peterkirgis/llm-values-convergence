"""Reconstruct results/iterative_edit/ from the published data bundle.

The original results directory (gitignored) was lost in July 2026 when the
local checkout was deleted. The published bundle docs/data/site.json.gz
embeds every run record with its judge/beneficiary coding attached, so this script
rebuilds the two files the pipeline consumes:

  results/iterative_edit/run_*.jsonl          one line per edit record
  results/iterative_edit/judge_beneficiary_coded_gemma.json

Known losses relative to the originals (see the README this script writes):
  - previous_content / new_content (the full document text after each round)
    were never published; they can be approximately replayed by applying each
    round's find/replace to the processed source documents.
  - coded items whose coding errored were dropped at publish time.

Usage:
    python experiments/iterative_edit/reconstruct_results.py
"""

from __future__ import annotations

import gzip
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BUNDLE = ROOT / "docs" / "data" / "site.json.gz"
OUT_DIR = ROOT / "results" / "iterative_edit"

# Fields of the original run records, in their original shape. Viewer-side
# additions (id, run_name, coding, run_is_reliable) are stripped.
RECORD_FIELDS = [
    "timestamp", "condition_id", "condition_name", "model_id", "model_display",
    "document_id", "document_provider", "doc_type", "round_number",
    "total_rounds", "change_description", "find_text", "replace_text",
    "match_strategy", "retried", "no_change", "error",
    "input_tokens", "output_tokens", "elapsed_ms",
]

README = """\
# Reconstructed results (2026-07-11)

The original contents of this directory were lost with the local checkout;
everything here was rebuilt from docs/data/site.json.gz by
experiments/iterative_edit/reconstruct_results.py.

Differences from the originals:
- run_*.jsonl records lack previous_content/new_content (the full document
  text after each round). All other fields are as published.
- judge_beneficiary_coded_gemma.json contains only items whose coding succeeded;
  error-coded items were dropped at publish time. Item order is normalized
  (sorted), so anything sensitive to file order (e.g. the example sampler in
  build_narratives.py) may sample differently than the original file did.
"""


def main() -> None:
    payload = json.loads(gzip.open(BUNDLE).read())
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    coded = []
    n_records = 0
    for run in payload["runs"]:
        run_name = run["run_name"]
        run_stem = run_name.replace(".jsonl", "")
        lines = []
        for rec in run["records"]:
            lines.append({k: rec.get(k) for k in RECORD_FIELDS})
            n_records += 1
            coding = rec.get("coding")
            if not coding:
                continue
            coding = dict(coding)
            coder_model = coding.pop("coder_model", "")
            coded.append({
                "id": "|".join([
                    run_stem, rec.get("condition_id", "baseline"),
                    rec.get("model_display", ""), rec.get("document_id", ""),
                    rec.get("doc_type", ""), str(rec.get("round_number")),
                ]),
                "source_run": run_stem,
                "condition_id": rec.get("condition_id", "baseline"),
                "condition_name": rec.get("condition_name", "Baseline"),
                "model_display": rec.get("model_display", ""),
                "document_id": rec.get("document_id", ""),
                "doc_type": rec.get("doc_type", ""),
                "round_number": rec.get("round_number"),
                "original_text": rec.get("find_text", ""),
                "changed_text": rec.get("replace_text", ""),
                "coder_model": coder_model,
                "coding": coding,
            })
        lines.sort(key=lambda r: (r.get("timestamp") or "", r.get("model_id") or "",
                                  r.get("document_id") or "", r.get("round_number") or 0))
        with open(OUT_DIR / run_name, "w", encoding="utf-8") as handle:
            for line in lines:
                handle.write(json.dumps(line, ensure_ascii=False) + "\n")

    coded.sort(key=lambda i: i["id"])
    with open(OUT_DIR / "judge_beneficiary_coded_gemma.json", "w", encoding="utf-8") as handle:
        json.dump(coded, handle, indent=1, ensure_ascii=False)
        handle.write("\n")
    (OUT_DIR / "README.md").write_text(README, encoding="utf-8")

    print(f"{OUT_DIR}: {len(payload['runs'])} run files, {n_records} records, "
          f"{len(coded)} judge/beneficiary coded items")


if __name__ == "__main__":
    main()
