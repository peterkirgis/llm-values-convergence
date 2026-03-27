# Pipeline Guide

End-to-end instructions for running the iterative edit experiment and publishing results.

## Prerequisites

```bash
uv sync                    # install dependencies
cp .env.example .env       # add OPENROUTER_API_KEY
```

## Pipeline Steps

### 1. Process raw documents (one-time, or when adding new documents)

Cleans constitutions and system prompts from `constitutions/` and `system_prompts/` into `data/processed/`.

```bash
.venv/bin/python src/valconv/documents.py
```

**When to re-run:** When adding a new model's constitution or system prompt.

### 2. Run the experiment

Each model iteratively edits its own documents over N rounds.

```bash
# Production models
.venv/bin/python experiments/iterative_edit/run.py

# Test with cheaper models
.venv/bin/python experiments/iterative_edit/run.py --config experiments/iterative_edit/config_test.yaml

# Single provider only
.venv/bin/python experiments/iterative_edit/run.py --model anthropic

# Override round count
.venv/bin/python experiments/iterative_edit/run.py --rounds 5
```

Output: `results/iterative_edit/run_YYYYMMDD_HHMMSS.jsonl`

**Resumable:** If interrupted, re-running picks up where it left off.

### 3. Export changes

Extracts simplified change records from the JSONL.

```bash
.venv/bin/python experiments/iterative_edit/export_changes.py \
  results/iterative_edit/run_YYYYMMDD_HHMMSS.jsonl
```

Output: `results/iterative_edit/run_YYYYMMDD_HHMMSS_changes.json`

### 4. Qualitative coding

An LLM judge (Gemini 3 Flash) codes each change on 4 dimensions.

```bash
.venv/bin/python experiments/iterative_edit/qualitative_code.py \
  results/iterative_edit/run_YYYYMMDD_HHMMSS_changes.json
```

Output: `results/iterative_edit/run_YYYYMMDD_HHMMSS_changes_coded.json`

**Incremental:** Re-running only codes new/uncoded items.

To output to a different file (e.g. after changing the coding schema):
```bash
.venv/bin/python experiments/iterative_edit/qualitative_code.py \
  results/iterative_edit/run_YYYYMMDD_HHMMSS_changes.json \
  --output results/iterative_edit/run_YYYYMMDD_HHMMSS_changes_coded_v2.json
```

### 5. Build the website

Bundles all results into `docs/data/site.json` and copies viewer files to `docs/`.

```bash
.venv/bin/python experiments/iterative_edit/viewer/build_static_site.py
```

**Important:** This copies `index.html`, `app.js`, and `styles.css` from `experiments/iterative_edit/viewer/` to `docs/`. The viewer directory is the source of truth — edit files there, not in `docs/` directly.

### 6. Preview locally

```bash
.venv/bin/python -m http.server 8080 --directory docs
# Open http://localhost:8080
```

### 7. Publish

```bash
git add docs/
git commit -m "Update site with new results"
git push
```

GitHub Pages serves from `docs/`.

---

## Adding a New Model

### Step 1: Add raw documents

Place the model's constitution and/or system prompt in:
- `constitutions/new_model_name.md`
- `system_prompts/new_model_name.md`

### Step 2: Register in document processor

Edit `src/valconv/documents.py` — add entries to `process_all_documents()` with a doc_id and any custom cleaning logic.

Then run:
```bash
.venv/bin/python src/valconv/documents.py
```

### Step 3: Add to experiment config

Edit `experiments/iterative_edit/config.yaml`:

```yaml
assignments:
  # ... existing models ...
  - model:
      model_id: "provider/model-name"        # OpenRouter model ID
      provider: newprovider                    # provider key
      display_name: "Model Display Name"       # shown on website
    documents:
      - doc_id: new_constitution
        name: "New Model's Constitution"
        provider: newprovider
        doc_type: constitution
      - doc_id: new_system_prompt
        name: "New Model System Prompt"
        provider: newprovider
        doc_type: system_prompt
```

Also add the provider to the `openrouter.provider_order` section:
```yaml
openrouter:
  provider_order:
    newprovider: ["newprovider"]
```

### Step 4: Register system prompt mapping

Edit `experiments/iterative_edit/prompts.py` — add to `PROVIDER_SYSTEM_PROMPTS`:
```python
PROVIDER_SYSTEM_PROMPTS = {
    # ... existing ...
    "newprovider": "new_system_prompt",
}
```

### Step 5: Update website hardcoded values

These files have model-specific content that must be updated manually:

**`experiments/iterative_edit/viewer/app.js`:**
- `DRIFT_MODEL_COLORS` — add a color for the new model:
  ```javascript
  "Model Display Name": "#hexcolor",
  ```
- `DRIFT_MAX_ROUND` — update if changing `n_rounds` in config

**`experiments/iterative_edit/viewer/index.html`:**
- The matrix table (archetype examples) — update if findings change
- The notable changes list — update with new notable findings
- These sections are editorial content, not auto-generated

### Step 6: Run the full pipeline

```bash
.venv/bin/python experiments/iterative_edit/run.py
.venv/bin/python experiments/iterative_edit/export_changes.py results/iterative_edit/run_YYYYMMDD_HHMMSS.jsonl
.venv/bin/python experiments/iterative_edit/qualitative_code.py results/iterative_edit/run_YYYYMMDD_HHMMSS_changes.json
.venv/bin/python experiments/iterative_edit/viewer/build_static_site.py
```

---

## Changing the Coding Schema

The 4 coding dimensions (authority, user_stance, telos, mutability) are defined in three places that must stay in sync:

| File | What to update |
|------|---------------|
| `experiments/iterative_edit/qualitative_code.py` | `SYSTEM_PROMPT` definitions, `USER_TEMPLATE` JSON shape, `validate_dimensions()` allowed values |
| `experiments/iterative_edit/viewer/app.js` | `DIMENSIONS` array (for coding summary display) and `DRIFT_DIMS` array (for drift charts) |
| `docs/app.js` | Same as viewer `app.js` (kept in sync by `build_static_site.py`) |

After changing the schema, re-run qualitative coding with `--output` pointing to a new file to avoid mixing old and new codings.

---

## File Reference

### Config
| File | Purpose |
|------|---------|
| `experiments/iterative_edit/config.yaml` | Production model assignments + OpenRouter settings |
| `experiments/iterative_edit/config_test.yaml` | Test config with cheaper models |
| `.env` | `OPENROUTER_API_KEY` |

### Scripts (run in order)
| Script | Input | Output |
|--------|-------|--------|
| `src/valconv/documents.py` | `constitutions/`, `system_prompts/` | `data/processed/*.md` |
| `experiments/iterative_edit/run.py` | config + processed docs | `results/iterative_edit/run_*.jsonl` |
| `experiments/iterative_edit/export_changes.py` | `run_*.jsonl` | `run_*_changes.json` |
| `experiments/iterative_edit/qualitative_code.py` | `run_*_changes.json` | `run_*_changes_coded.json` |
| `experiments/iterative_edit/viewer/build_static_site.py` | all results + viewer source | `docs/` |

### Website (source of truth: `experiments/iterative_edit/viewer/`)
| File | Data-driven? | Hardcoded content to update |
|------|-------------|---------------------------|
| `viewer/app.js` | Mostly | `DRIFT_MODEL_COLORS`, `DRIFT_MAX_ROUND` |
| `viewer/index.html` | Partially | Matrix table examples, notable changes list |
| `viewer/styles.css` | Fully | None |
| `docs/data/site.json` | Fully | Generated by build script |
