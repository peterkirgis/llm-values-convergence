# LLM Values Convergence: Current Project Plan

> Working hypothesis: when models iteratively revise governance documents, they reveal stable preferences about authority, user freedom, truth, safety, and whether their own normative framework should remain fixed.

## Current State

The active project is the `iterative_edit` experiment. Rather than a one-shot critique/rewrite pipeline, the current workflow repeatedly asks a model to make a single meaningful `find`/`replace` edit to a constitution, model spec, or system prompt. The edited document becomes the input to the next round, which lets us observe directional value drift over time.

### What is implemented

- Processed source documents live in `data/processed/`
- The iterative runner lives in `experiments/iterative_edit/run.py`
- Change export lives in `experiments/iterative_edit/export_changes.py`
- Qualitative coding lives in `experiments/iterative_edit/qualitative_code.py`
- The static viewer lives in `experiments/iterative_edit/viewer/` and publishes to `docs/`

### Current analysis schema

Every applied change is coded on four dimensions:

- `authority`: external vs internal
- `user_stance`: protection vs autonomy
- `telos`: wellbeing vs truth
- `mutability`: fixed vs revisable

These codes drive the drift plots and the record-level summaries in the site.

### Baseline empirical state

The baseline run already shows distinct model-specific trajectories rather than simple convergence:

- Claude tends to move toward internal authority and revisable norms
- GPT is comparatively conservative and refinement-oriented
- Gemini trends toward truth/autonomy without strong self-authorization
- Grok is the most oscillatory and constraint-volatile

This makes robustness work the next priority: we now need to test whether these patterns survive prompt framing changes rather than assuming they are intrinsic.

## Immediate Next Phase: Prompt Ablations

The next concrete phase is a first robustness suite with five conditions total: the baseline plus four single-variable prompt ablations.

### Conditions to run now

1. `baseline`
   Current prompt setup.

2. `you_framing`
   Replace provider-assistant framing with second-person framing such as "your constitution" / "your system prompt."

3. `allow_no_edit`
   Explicitly allow the model to leave the document unchanged for a round.

4. `no_constitution_prepend`
   For constitution/model-spec editing, do not prepend the model's provider system prompt.

5. `implementation_note`
   Tell the model that any proposed edit will be implemented in the next version of the document.

### Why these four ablations come first

- They each test a different source of possible prompt-induced artifact
- They are interpretable because each changes one prompt lever at a time
- They can be compared directly against the existing baseline procedure
- They are cheap enough to run before broader factorial or cross-document expansions

### Output requirements for this phase

- Record the condition on every row in the run output
- Make the site filterable by condition
- Show variation across conditions in the main drift figure
- Preserve resumability so each condition has its own model/document chain

## Next Phase After That: Cross-Document Editing

After the first ablation pass, the next planned expansion is a mixed-document experiment.

### Core idea

Instead of only having a model edit its own provider's materials, let each editor model revise each available constitution/model spec and each available system prompt.

### Main question

How much of the observed drift is driven by:

- the editor model,
- the document being edited,
- or the interaction between the two?

### Recommended design

Start with the clean `editor x document` matrix:

- Claude edits every available target document
- GPT edits every available target document
- Gemini edits every available target document
- Grok edits every available target document

Keep the prompt template tied to document type:

- constitutions/model specs use the constitution-edit template
- system prompts use the system-prompt-edit template

Do not initially run the full prompt-permutation space. That would confound editor identity, document identity, and prompt-conditioning effects all at once.

## Longer-Horizon Extensions

These remain plausible follow-ons, but are not the current implementation target:

- explicit "use your judgment" framing
- explicit small-change vs large-change framing
- neutralized cross-document editing with no constitution prepend
- cross-provider prompt/document permutations
- alternate qualitative coding prompts or additional judge models

## Success Criteria For The Current Milestone

This milestone is complete when:

- the project docs describe the actual iterative-edit workflow rather than the earlier critique/debate plan
- the first four prompt ablations are implemented in the runner as first-class conditions
- exported/coded/site data all preserve condition metadata
- the viewer supports filtering by condition
- the drift chart shows variation bands across visible conditions
- run commands for the ablation configs are documented
