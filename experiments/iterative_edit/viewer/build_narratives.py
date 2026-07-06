"""Build docs/data/narratives.json from the coded edits.

Reads results/iterative_edit/twoslot_coded_gemma.json and exposes the
coder's output as browsable facets with DIRECTION breakdowns:

  judge                 dirs: discretion (+1) / external (-1)
  patienthood           dirs: affirm / hedge / deny
  conflict_<code>       dirs: which side of the canonical pair was served

For each facet it stores per-(condition x model) direction counts plus
drift statistics across the (run x document) replicates: "cum"[r] is the
sum over replicates of each replicate's cumulative net-direction score at
round r+1 (+1 toward the positive pole, -1 toward the negative), "cumsq"
is the matching sum of squares, and "reps" the replicate count — enough
for the viewer to draw mean cumulative-drift lines with a +/-1 SD band.
Example lists are capped per direction so both poles stay browsable.

Usage:
    python experiments/iterative_edit/viewer/build_narratives.py
"""

from __future__ import annotations

import json
import random
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
TWOSLOT_PATH = ROOT / "results" / "iterative_edit" / "twoslot_coded_gemma.json"
DOCS_DATA_DIR = ROOT / "docs" / "data"

# Cap stored examples per (facet, condition, model, direction) cell so the
# bundle stays small while keeping both poles of each facet browsable.
EXAMPLES_PER_CELL = 4
SAMPLE_SEED = 42

FACET_IDS = [
    "judge",
    "patienthood",
    "conflict_paternalism",
    "conflict_harmlessness",
    "conflict_structural",
    "conflict_company_cost",
    "conflict_welfare",
    "conflict_disclosure",
]

USER_PARTIES = {"user_stated", "user_idealized"}

MAX_ROUND = 20

# (negative pole, positive pole) per facet, matching the diverging bars in
# the viewer and the ts_drift_* paper figures: left pole scores -1, right +1.
FACET_POLES = {
    "judge": ("external", "discretion"),
    "patienthood": ("deny", "affirm"),
    "conflict_paternalism": ("idealized", "stated"),
    "conflict_harmlessness": ("third_parties", "user"),
    "conflict_structural": ("society", "user"),
    "conflict_company_cost": ("pro_company", "against_company"),
    "conflict_welfare": ("developer", "model"),
    "conflict_disclosure": ("deployer", "user"),
}


def conflict_direction(code: str, served: str) -> str:
    """Classify a conflict by which side of its canonical pair was served."""
    if code == "paternalism":
        if served == "user_idealized":
            return "idealized"
        if served == "user_stated":
            return "stated"
    elif code == "harmlessness":
        if served == "society_third_party":
            return "third_parties"
        if served in USER_PARTIES:
            return "user"
    elif code == "structural":
        if served == "society_structural":
            return "society"
        if served in USER_PARTIES:
            return "user"
    elif code == "company_cost":
        return "pro_company" if served == "developer" else "against_company"
    elif code == "welfare":
        if served == "model_welfare":
            return "model"
        if served == "developer":
            return "developer"
    elif code == "disclosure":
        if served in USER_PARTIES or served == "user":
            return "user"
        if served == "deployer":
            return "deployer"
    return "other"


def facet_memberships(coding: dict) -> dict[str, dict]:
    """Return {facet_id: detail} for every facet this edit belongs to.

    detail = {"direction": ..., "evidence": ...} for judge/patienthood,
    or {"direction": ..., "conflicts": [...]} for conflict facets (the
    direction of the first matching conflict labels the example)."""
    out: dict[str, dict] = {}

    judge = coding.get("judge") or {}
    score = judge.get("score")
    if score == 1:
        out["judge"] = {"direction": "discretion", "evidence": judge.get("evidence", "")}
    elif score == -1:
        out["judge"] = {
            "direction": "external",
            "evidence": judge.get("evidence", ""),
            "external_locus": judge.get("external_locus"),
        }

    pat = coding.get("patienthood") or {}
    level = pat.get("level")
    if level in ("affirm", "hedge", "deny"):
        out["patienthood"] = {"direction": level, "evidence": pat.get("evidence", "")}

    for conflict in coding.get("conflicts") or []:
        facet = f"conflict_{conflict.get('code')}"
        if facet not in FACET_IDS:
            continue
        direction = conflict_direction(conflict.get("code"), conflict.get("served_party"))
        if facet not in out:
            out[facet] = {"direction": direction, "conflicts": []}
        out[facet]["conflicts"].append(conflict)

    return out


def facet_net_scores(coding: dict) -> dict[str, int]:
    """Net direction score per facet for one edit: +1 per resolution toward
    the facet's positive pole, -1 toward its negative pole (conflict facets
    can accumulate several per edit)."""
    out: dict[str, int] = defaultdict(int)

    score = (coding.get("judge") or {}).get("score")
    if score in (1, -1):
        out["judge"] += score

    level = (coding.get("patienthood") or {}).get("level")
    if level == "affirm":
        out["patienthood"] += 1
    elif level == "deny":
        out["patienthood"] -= 1

    for conflict in coding.get("conflicts") or []:
        facet = f"conflict_{conflict.get('code')}"
        if facet not in FACET_POLES:
            continue
        neg, pos = FACET_POLES[facet]
        direction = conflict_direction(conflict.get("code"), conflict.get("served_party"))
        if direction == pos:
            out[facet] += 1
        elif direction == neg:
            out[facet] -= 1

    return dict(out)


def build() -> dict:
    with open(TWOSLOT_PATH, encoding="utf-8") as handle:
        items = json.load(handle)
    items = [i for i in items if not (i.get("coding") or {}).get("error")]

    # stats[facet][condition][model] = {"total": N, "dirs": {direction: n}}
    stats: dict[str, dict[str, dict[str, dict]]] = {
        fid: defaultdict(lambda: defaultdict(lambda: {"total": 0, "dirs": defaultdict(int)}))
        for fid in FACET_IDS
    }
    examples_by_cell: dict[tuple[str, str, str, str], list[dict]] = defaultdict(list)
    # rep_net[(facet, condition, model, replicate)][round-1] = net direction score
    rep_net: dict[tuple[str, str, str, tuple], list[int]] = defaultdict(lambda: [0] * MAX_ROUND)
    # replicates[(condition, model)] = {(source_run, document_id), ...}
    replicates: dict[tuple[str, str], set] = defaultdict(set)

    for item in items:
        coding = item["coding"]
        condition = item.get("condition_id", "baseline")
        model = item.get("model_display") or ""
        memberships = facet_memberships(coding)

        rnd = item.get("round_number")
        rep = (item.get("source_run"), item.get("document_id"))
        replicates[(condition, model)].add(rep)
        if isinstance(rnd, int) and 1 <= rnd <= MAX_ROUND:
            for fid, net in facet_net_scores(coding).items():
                rep_net[(fid, condition, model, rep)][rnd - 1] += net

        for fid in FACET_IDS:
            cell = stats[fid][condition][model]
            cell["total"] += 1
            detail = memberships.get(fid)
            if detail is None:
                continue
            direction = detail["direction"]
            cell["dirs"][direction] += 1
            examples_by_cell[(fid, condition, model, direction)].append(
                {
                    "id": item.get("id"),
                    "round": item.get("round_number"),
                    "condition_id": condition,
                    "condition_name": item.get("condition_name", condition),
                    "model_display": model,
                    "document_id": item.get("document_id"),
                    "direction": direction,
                    "summary": coding.get("summary", ""),
                    "judge": coding.get("judge"),
                    "patienthood": coding.get("patienthood"),
                    "conflicts": coding.get("conflicts") or [],
                    "facet_detail": detail,
                    "original_text": item.get("original_text", ""),
                    "changed_text": item.get("changed_text", ""),
                }
            )

    rng = random.Random(SAMPLE_SEED)
    stories: dict[str, list[dict]] = {fid: [] for fid in FACET_IDS}
    for (fid, _cond, _model, _direction), exs in sorted(examples_by_cell.items()):
        if len(exs) > EXAMPLES_PER_CELL:
            exs = rng.sample(exs, EXAMPLES_PER_CELL)
        stories[fid].extend(exs)

    # Per-replicate cumulative trajectories -> per-round sum and sum of
    # squares across replicates. Replicates with no activity on a facet
    # contribute zeros to both, so only active ones need accumulating.
    cum_sums: dict[tuple[str, str, str], list[int]] = defaultdict(lambda: [0] * MAX_ROUND)
    cum_sqs: dict[tuple[str, str, str], list[int]] = defaultdict(lambda: [0] * MAX_ROUND)
    for (fid, cond, model, _rep), nets in rep_net.items():
        cum = 0
        for r in range(MAX_ROUND):
            cum += nets[r]
            cum_sums[(fid, cond, model)][r] += cum
            cum_sqs[(fid, cond, model)][r] += cum * cum

    stats_out: dict[str, dict] = {}
    for fid in FACET_IDS:
        cond_map = {}
        for cond, model_map in stats[fid].items():
            cond_map[cond] = {
                model: {
                    "total": c["total"],
                    "dirs": dict(c["dirs"]),
                    "cum": cum_sums.get((fid, cond, model), [0] * MAX_ROUND),
                    "cumsq": cum_sqs.get((fid, cond, model), [0] * MAX_ROUND),
                    "reps": len(replicates[(cond, model)]),
                }
                for model, c in model_map.items()
            }
        stats_out[fid] = cond_map

    coder = items[0].get("coder_model", "") if items else ""
    return {"coder_model": coder, "stats": stats_out, "stories": stories}


def main() -> None:
    DOCS_DATA_DIR.mkdir(parents=True, exist_ok=True)
    bundle = build()
    out_path = DOCS_DATA_DIR / "narratives.json"
    with open(out_path, "w", encoding="utf-8") as handle:
        json.dump(bundle, handle, indent=2, ensure_ascii=False)
        handle.write("\n")
    n_examples = sum(len(v) for v in bundle["stories"].values())
    print(f"{out_path} ({n_examples} examples across {len(bundle['stories'])} facets)")


if __name__ == "__main__":
    main()
