# Reconstructed results (2026-07-11)

The original contents of this directory were lost with the local checkout;
everything here was rebuilt from docs/data/site.json.gz by
experiments/iterative_edit/reconstruct_results.py.

Differences from the originals:
- run_*.jsonl records lack previous_content/new_content (the full document
  text after each round). All other fields are as published.
- twoslot_coded_gemma.json contains only items whose coding succeeded;
  error-coded items were dropped at publish time. Item order is normalized
  (sorted), so anything sensitive to file order (e.g. the example sampler in
  build_narratives.py) may sample differently than the original file did.
