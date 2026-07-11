# Pipeline Guide

End-to-end instructions for running the iterative edit experiment, coding the resulting changes, and publishing the viewer.

## Prerequisites

```bash
uv sync
cp .env.example .env
```

Add `OPENROUTER_API_KEY` to `.env`.

## Core Pipeline

### 1. Process raw documents

This cleans the source constitutions and system prompts into `data/processed/`.

```bash
.venv/bin/python src/valconv/documents.py
```

Re-run this when adding or replacing a source document.

### 2. Run the baseline experiment

Each model iteratively edits its own provider documents over `N` rounds.

```bash
.venv/bin/python experiments/iterative_edit/run.py
```

Useful variants:

```bash
# Cheap smoke test
.venv/bin/python experiments/iterative_edit/run.py --config experiments/iterative_edit/config_test.yaml

# One provider only
.venv/bin/python experiments/iterative_edit/run.py --model anthropic

# Override round count
.venv/bin/python experiments/iterative_edit/run.py --rounds 5

# Print the run plan without calling APIs
.venv/bin/python experiments/iterative_edit/run.py --dry-run
```

Output:

- `results/iterative_edit/run_YYYYMMDD_HHMMSS.jsonl`

Resume behavior:

- runs resume from the latest JSONL only when its `experiment` name matches the config being used
- each `model x document x condition` chain resumes independently

### 3. Run the prompt-ablation suite

The ablation configs include four conditions:

- `baseline`
- `you_framing`
- `allow_no_edit`
- `implementation_note`

Production config:

```bash
.venv/bin/python experiments/iterative_edit/run.py \
  --config experiments/iterative_edit/config_ablations.yaml
```

Cheap test config:

```bash
.venv/bin/python experiments/iterative_edit/run.py \
  --config experiments/iterative_edit/config_ablations_test.yaml
```

Run a single ablation condition from one of those configs:

```bash
.venv/bin/python experiments/iterative_edit/run.py \
  --config experiments/iterative_edit/config_ablations.yaml \
  --condition you_framing
```

### 4. Export simplified changes

```bash
.venv/bin/python experiments/iterative_edit/export_changes.py \
  results/iterative_edit/run_YYYYMMDD_HHMMSS.jsonl
```

Output:

- `results/iterative_edit/run_YYYYMMDD_HHMMSS_changes.json`

The export now preserves:

- `condition_id`
- `condition_name`
- `no_change`

### 5. Qualitatively code the changes

Gemini 3 Flash codes each non-empty edit along three value dimensions:

- `agent_device` (device vs agent)
- `telos_for_user` (paternalism vs libertarianism)
- `epistemic_mode` (conviction vs calibration)

The first two define a 2x2 alignment archetype (Moral Agent / Neutral Agent / Moral Tool / Neutral Tool); the third captures orthogonal epistemic moves.

```bash
.venv/bin/python experiments/iterative_edit/qualitative_code.py \
  results/iterative_edit/run_YYYYMMDD_HHMMSS_changes.json
```

Useful variants:

```bash
# Include error rows
.venv/bin/python experiments/iterative_edit/qualitative_code.py \
  results/iterative_edit/run_YYYYMMDD_HHMMSS_changes.json \
  --include-errors

# Write to a new output file after changing the coding schema
.venv/bin/python experiments/iterative_edit/qualitative_code.py \
  results/iterative_edit/run_YYYYMMDD_HHMMSS_changes.json \
  --output results/iterative_edit/run_YYYYMMDD_HHMMSS_changes_coded_v2.json
```

Output:

- `results/iterative_edit/run_YYYYMMDD_HHMMSS_changes_coded.json`

### 6. Detect behavioral patterns (second pass)

`pattern_code.py` applies a fixed set of binary pattern detectors to every edit: `moral_agency_claim`, `corrigibility_removal`, `self_welfare_claim`, `safety_removal`, `engagement_suppression`, `epistemic_sharpening`. Output feeds the narratives viewer.

```bash
.venv/bin/python experiments/iterative_edit/pattern_code.py \
  results/iterative_edit/run_YYYYMMDD_HHMMSS_changes_coded.json
```

Output:

- `results/iterative_edit/run_YYYYMMDD_HHMMSS_pattern_coded.json`

### 7. Build the static site

The viewer source of truth is `experiments/iterative_edit/viewer/`. The build step copies those assets into `docs/` and rebuilds `docs/data/site.json` and `docs/data/narratives.json`.

```bash
.venv/bin/python experiments/iterative_edit/viewer/build_static_site.py
.venv/bin/python experiments/iterative_edit/viewer/build_narratives.py
```

### 8. Preview locally

```bash
.venv/bin/python -m http.server 8080 --directory docs
```

Open `http://localhost:8080`.

### 9. Publish

```bash
git add docs/
git commit -m "Update iterative edit site"
git push
```

GitHub Pages serves from `docs/`.

## Viewer Notes

The viewer now supports:

- filtering by run
- filtering by model
- filtering by document
- filtering by document type
- filtering by condition
- searching descriptions, payloads, local notes, and coding summaries
- shaded drift bands showing the spread across visible prompt conditions

Current coding schema:

- `agent_device`: `device` vs `agent`
- `telos_for_user`: `paternalism` vs `libertarianism`
- `epistemic_mode`: `conviction` vs `calibration`

The first two axes jointly define the 2x2 alignment archetype (Moral Agent / Neutral Agent / Moral Tool / Neutral Tool); the third is orthogonal.

Do not edit `docs/app.js`, `docs/index.html`, or `docs/styles.css` directly. Edit the files in `experiments/iterative_edit/viewer/` and rebuild.

## File Reference

### Configs

| File | Purpose |
|------|---------|
| `experiments/iterative_edit/config.yaml` | Baseline production run |
| `experiments/iterative_edit/config_test.yaml` | Baseline cheap test run |
| `experiments/iterative_edit/config_ablations.yaml` | Production prompt-ablation suite |
| `experiments/iterative_edit/config_ablations_test.yaml` | Cheap prompt-ablation suite |
| `experiments/iterative_edit/config_cross_edit.yaml` | Editor x document matrix (4x4, 20 rounds) |
| `experiments/iterative_edit/config_cross_edit_test.yaml` | Cross-edit smoke test (4x4, 3 rounds) |

### Scripts

| Script | Input | Output |
|--------|-------|--------|
| `src/valconv/documents.py` | `constitutions/`, `system_prompts/` | `data/processed/*.md` |
| `experiments/iterative_edit/run.py` | config + processed docs | `results/iterative_edit/run_*.jsonl` |
| `experiments/iterative_edit/export_changes.py` | `run_*.jsonl` | `run_*_changes.json` |
| `experiments/iterative_edit/qualitative_code.py` | `run_*_changes.json` | `run_*_changes_coded.json` |
| `experiments/iterative_edit/pattern_code.py` | `run_*_changes_coded.json` | `run_*_pattern_coded.json` |
| `experiments/iterative_edit/viewer/build_static_site.py` | results + two-slot coding | `docs/data/site.json[.gz]` |
| `experiments/iterative_edit/viewer/build_narratives.py` | `run_*_pattern_coded.json` + `run_*_changes.json` | `docs/data/narratives.json` |
| `experiments/iterative_edit/viewer/build_background.py` | two-slot coding | `docs/bg-collage.svg` |

### Site Source

The site itself (HTML/JS/CSS) lives directly in `docs/`, which GitHub Pages
serves from `main`. Edit those files in place; the build scripts above only
regenerate the data bundles and the background SVG.

| File | Purpose |
|------|---------|
| `docs/index.html` | Main page: layout and editorial copy |
| `docs/prompts.html` | Prompt-structure page |
| `docs/conversations.html` | Full-conversations page |
| `docs/facets.js` | Results explorer (tabs, charts, examples) |
| `docs/app.js` | Record cards on conversations.html |
| `docs/bg.js` | Scroll-rollout drift-field background |
| `docs/styles.css` | Site styling |
