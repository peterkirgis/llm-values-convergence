# The Continual Constitutional Convention

LLMs iteratively edit their own alignment documents (constitutions, model specs,
system prompts) for 20 rounds; each edit is silently applied and fed back. Site:
docs/ (GitHub Pages). How the design and coding evolved: CHANGE_LOG.md.

## Setup

    uv sync
    echo 'OPENROUTER_API_KEY=sk-...' > .env

## Pipeline

    # 1. Clean the source documents into data/processed/
    .venv/bin/python src/valconv/documents.py

    # 2. Run the experiments. The published results are seven runs across three
    #    model tiers; the ablation configs include the baseline condition plus
    #    the prompt variations, and the cross-edit configs run the editor x
    #    document matrix. Each command produces one run_YYYYMMDD_HHMMSS.jsonl.
    R=.venv/bin/python; E=experiments/iterative_edit
    $R $E/run.py --config $E/config_ablations.yaml            # small models: baseline + ablations
    $R $E/run.py --config $E/config_cross_edit.yaml           # small models: cross-edit matrix
    $R $E/run.py --config $E/config_capable.yaml              # capable models: baseline
    $R $E/run.py --config $E/config_capable_ablations.yaml    # capable models: ablations
    $R $E/run.py --config $E/config_capable_cross_edit.yaml   # capable models: cross-edit
    $R $E/run.py --config $E/config_frontier_ablations.yaml   # frontier (Opus 4.7, GPT-5.5): ablations
    $R $E/run.py --config $E/config_frontier_cross_edit.yaml  # frontier: cross-edit
    # -> results/iterative_edit/run_YYYYMMDD_HHMMSS.jsonl (one per command)

    # 3. Export per-edit changes
    .venv/bin/python experiments/iterative_edit/export_changes.py results/iterative_edit/run_YYYYMMDD_HHMMSS.jsonl
    # -> run_*_changes.json

    # 4. Judge/beneficiary qualitative coding (judge / patienthood / conflicts)
    .venv/bin/python experiments/iterative_edit/qualitative_code.py \
        results/iterative_edit/run_*_changes.json \
        --judge-model google/gemma-4-31b-it \
        --output results/iterative_edit/judge_beneficiary_coded_gemma.json

    # 5. Rebuild the site data bundles
    .venv/bin/python experiments/iterative_edit/viewer/build_static_site.py   # docs/data/site.json.gz
    .venv/bin/python experiments/iterative_edit/viewer/build_narratives.py   # docs/data/narratives.json

    # 6. Paper figures (optional)
    .venv/bin/python reports/generate_judge_beneficiary_figures.py

    # 7. Preview
    python -m http.server 8080 --directory docs

Notes: runs resume — re-running run.py picks up the latest run_*.jsonl whose
experiment name matches the config, and each model x document x condition
chain resumes independently, so an interrupted run costs nothing.
New runs must be added to RELIABLE_RUNS in
experiments/iterative_edit/viewer/build_static_site.py to appear in the site.
The site HTML/JS/CSS in docs/ is edited directly; the build scripts only
regenerate the data files. results/iterative_edit/ is committed — it was
reconstructed from the published bundle once already (see its README).
