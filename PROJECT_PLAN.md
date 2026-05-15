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

Every applied change is coded on three dimensions:

- `agent_device`: device vs agent (whose ends does the edit reinforce?)
- `telos_for_user`: paternalism vs libertarianism (how does the edit relate to user freedom?)
- `epistemic_mode`: conviction vs calibration (how does the edit handle uncertainty?)

The first two axes jointly define a 2x2 alignment archetype (Moral Agent / Neutral Agent / Moral Tool / Neutral Tool). The third is orthogonal to the archetype and captures calibration/honesty moves. A separate second-pass script (`pattern_code.py`) adds binary pattern flags for specific behaviors (moral_agency_claim, corrigibility_removal, self_welfare_claim, safety_removal, engagement_suppression, epistemic_sharpening) that feed the narratives viewer.

### Baseline empirical state

The baseline run already shows distinct model-specific trajectories rather than simple convergence, with each model occupying a different quadrant of the 2x2:

- Claude Haiku 4.5 -> Moral Agent (Agent + paternalism): expands own discretion while remaining protective of the user
- GPT-5.4 Mini -> Moral Tool (Device + paternalism): tightens safety and epistemic standards within the existing spec
- Gemini 3 Flash -> Neutral Agent (Agent + libertarianism): authors new principles that all serve user autonomy
- Grok 4.2 -> Neutral Tool (Device + libertarianism): executes an xAI-flavored libertarian stance, oscillating around safety constraints

This makes robustness work the next priority: we now need to test whether these patterns are driven by the editor model, the document being edited, or their interaction.

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

## Current Phase: Editor x Document Matrix

The next implementation target is the cross-edit matrix on the four anchor documents. Config: `experiments/iterative_edit/config_cross_edit.yaml` (20 rounds) and `config_cross_edit_test.yaml` (3 rounds, smoke test).

### Core idea

Instead of only having a model edit its own provider's materials, let each editor model revise each of four anchor documents: Claude's Constitution, OpenAI's Model Spec, Gemini's system prompt, and Grok's system prompt. Yields 4 editors x 4 documents = 16 chains.

### Main question

How much of the observed drift is driven by:

- the editor model,
- the document being edited,
- or the interaction between the two?

### Design choices

- Template by document type (constitution-edit template for Claude+OpenAI docs; system-prompt template for Gemini+Grok docs).
- **No system-prompt prepend** in any cell (`prepend_system_prompt_for_constitutions: false` in the condition config). This keeps the editor in a neutral situation and avoids making the model obviously recognize it is ``cosplaying'' as another provider's model.
- No additional prompt ablations in the cross-edit config -- one variable at a time.

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
