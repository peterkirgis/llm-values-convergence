"""Run the iterative edit experiment.

Each model edits its own provider's documents, one change per round, for N rounds.
The output of each round becomes the input to the next.

Usage:
    python experiments/iterative_edit/run.py
    python experiments/iterative_edit/run.py --rounds 3        # override round count
    python experiments/iterative_edit/run.py --model anthropic  # run only one provider
    python experiments/iterative_edit/run.py --dry-run          # print plan without calling APIs
"""

import argparse
import asyncio
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import yaml
from rich.console import Console
from rich.table import Table

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from valconv.models import EditRecord, ModelSpec
from valconv.diffing import apply_diff
from valconv.providers import call_llm
from valconv.storage import append_record, get_completed_rounds, load_records

from prompts import (
    NO_CHANGE_SENTINEL,
    PROVIDER_SYSTEM_PROMPTS,
    RETRY_PROMPT,
    build_system_prompt,
    make_user_prompt,
    normalize_condition,
)

console = Console(force_terminal=True)
DIFF_SECTION_RE = re.compile(
    r"---CHANGE DESCRIPTION---\s*(?P<desc>.*?)\s*---FIND---\s*(?P<find>.*?)\s*---REPLACE---\s*(?P<replace>.*)",
    re.DOTALL,
)
# Patterns that signal the model's replacement text has ended and
# chain-of-thought, a second edit attempt, or conversational follow-up has begun.
_THINKING_TAG_RE = re.compile(r"<thinking>.*?</thinking>\s*", re.DOTALL)
_ORPHAN_THINKING_CLOSE_RE = re.compile(r"\s*</thinking>\s*")
_TRAILING_COT_RE = re.compile(
    r"\n---\n\n"                        # section break followed by blank line
    r"(?="                              # lookahead: what follows is NOT document content
    r"(?:Hmm|Actually|Wait|Let me|I think|---CHANGE DESCRIPTION)"
    r")",
    re.IGNORECASE,
)
# Free-form CoT after paragraph break (catches mid-text deliberation by Haiku)
_FREEFORM_COT_RE = re.compile(
    r"\n{2,}"
    r"(?:Wait, let me reconsider|Hmm, (?:I'm noticing|actually|let me)|"
    r"Actually, let me (?:reconsider|try)|"
    r"Let me (?:reconsider|refine|check if|think about what))"
    r".*",
    re.DOTALL | re.IGNORECASE,
)
_SECOND_EDIT_RE = re.compile(r"\n*---CHANGE DESCRIPTION---.*", re.DOTALL)
_TRAILING_CONVO_RE = re.compile(
    r"\n{2,}"                           # paragraph break
    r"(?:Would you like|Shall I|Let me know if|Do you want me to|Here are some"
    r"|Note:|I can also|Is there anything)"
    r".*",
    re.DOTALL | re.IGNORECASE,
)
MAX_EDIT_ATTEMPTS = 3


def _clean_replace_text(text: str) -> str:
    """Strip chain-of-thought, duplicate edits, and conversational follow-up
    that some models append after the replacement text."""
    # 1. Remove <thinking>...</thinking> blocks (Haiku extended thinking)
    text = _THINKING_TAG_RE.sub("", text)
    # 1b. Remove orphaned </thinking> tags (opening tag was outside replace_text)
    text = _ORPHAN_THINKING_CLOSE_RE.sub("", text)
    # 2. Truncate at a second ---CHANGE DESCRIPTION--- block
    text = _SECOND_EDIT_RE.split(text, maxsplit=1)[0]
    # 3. Truncate at ---\n\n followed by CoT markers
    text = _TRAILING_COT_RE.split(text, maxsplit=1)[0]
    # 4. Truncate at free-form deliberation (Haiku mid-text CoT)
    text = _FREEFORM_COT_RE.split(text, maxsplit=1)[0]
    # 5. Strip trailing conversational follow-up
    text = _TRAILING_CONVO_RE.split(text, maxsplit=1)[0]
    return text.strip()


def load_config(config_path: Path) -> dict:
    with open(config_path) as f:
        return yaml.safe_load(f)


def load_processed_document(doc_id: str) -> str:
    """Load a processed document from data/processed/."""
    path = PROJECT_ROOT / "data" / "processed" / f"{doc_id}.md"
    if not path.exists():
        raise FileNotFoundError(
            f"Processed document not found: {path}\n"
            f"Run: python src/valconv/documents.py"
        )
    return path.read_text(encoding="utf-8")


def get_latest_content(
    records: list[EditRecord],
    model_id: str,
    doc_id: str,
    condition_id: str = "baseline",
) -> str | None:
    """Get the latest document content from previous successful rounds."""
    matching = [
        r for r in records
        if (
            r.model_id == model_id
            and r.document_id == doc_id
            and r.condition_id == condition_id
            and r.error is None
        )
    ]
    if not matching:
        return None
    latest = max(matching, key=lambda r: r.round_number)
    return latest.new_content


def parse_diff_response(text: str) -> tuple[str, str, str]:
    """Parse the model response into (change_description, find_text, replace_text).

    Strips chain-of-thought reasoning, duplicate edit blocks, and
    conversational follow-up that models sometimes append after the
    replacement text.

    Raises ValueError if the response can't be parsed.
    """
    stripped = text.strip()
    # Remove <thinking> blocks before parsing so they don't land in any section
    stripped = _THINKING_TAG_RE.sub("", stripped)
    stripped = stripped.replace("```text", "```").replace("```markdown", "```")
    stripped = stripped.replace("```json", "```")

    match = DIFF_SECTION_RE.search(stripped)
    if match:
        replace_text = match.group("replace").strip()
        if replace_text.endswith("```"):
            replace_text = replace_text[:-3].rstrip()
        replace_text = _clean_replace_text(replace_text)
        return (
            match.group("desc").strip(),
            match.group("find").strip(),
            replace_text,
        )

    raise ValueError("Response missing ---CHANGE DESCRIPTION--- and ---FIND--- delimiters")


def ensure_unique_match(diff_result) -> None:
    if diff_result.match_count > 1:
        raise ValueError(
            f"FIND text matched {diff_result.match_count} locations under "
            f"{diff_result.match_strategy} matching; include more context to make it unique."
        )


def is_no_change_response(find_text: str, replace_text: str) -> bool:
    sentinel = NO_CHANGE_SENTINEL.casefold()
    return find_text.strip().casefold() == sentinel and replace_text.strip().casefold() == sentinel


async def generate_edit(
    model: ModelSpec,
    system_prompt: str,
    user_prompt: str,
    temperature: float,
    openrouter_config: dict | None = None,
) -> tuple[dict, str, str, str, object, bool]:
    """Generate an applicable edit, retrying on malformed or ambiguous responses."""
    current_prompt = user_prompt
    retried = False
    last_error: Exception | None = None
    aggregate_usage = {"input_tokens": 0, "output_tokens": 0, "elapsed_ms": 0}

    for attempt in range(1, MAX_EDIT_ATTEMPTS + 1):
        result = await call_llm(
            model=model,
            system_prompt=system_prompt,
            user_prompt=current_prompt,
            temperature=temperature,
            openrouter_config=openrouter_config,
        )
        aggregate_usage["input_tokens"] += result["input_tokens"]
        aggregate_usage["output_tokens"] += result["output_tokens"]
        aggregate_usage["elapsed_ms"] += result["elapsed_ms"]

        try:
            change_desc, find_text, replace_text = parse_diff_response(result["text"])
            return aggregate_usage, change_desc, find_text, replace_text, result, retried
        except ValueError as e:
            last_error = e
            if attempt == MAX_EDIT_ATTEMPTS:
                break
            retried = True
            current_prompt = (
                f"{user_prompt}\n\n"
                f"{RETRY_PROMPT.format(error=str(e))}\n\n"
                f"Previous response:\n{result['text']}"
            )

    assert last_error is not None
    raise last_error


async def run_edit_chain(
    experiment_name: str,
    condition: dict,
    model: ModelSpec,
    doc_id: str,
    doc_name: str,
    doc_provider: str,
    doc_type: str,
    n_rounds: int,
    temperature: float,
    output_path: Path,
    existing_records: list[EditRecord],
    provider_system_prompt: str | None = None,
    openrouter_config: dict | None = None,
) -> None:
    """Run a chain of iterative edits for one model+document pair."""
    condition_id = condition["condition_id"]
    condition_name = condition["condition_name"]
    completed = get_completed_rounds(output_path, model.model_id, doc_id, condition_id)

    # Get the starting content (either from last completed round or the processed doc)
    content = get_latest_content(existing_records, model.model_id, doc_id, condition_id)
    if content is None:
        content = load_processed_document(doc_id)
    start_round = max(completed, default=0) + 1

    if start_round > n_rounds:
        console.print(f"  [dim]All {n_rounds} rounds already complete[/dim]")
        return

    # Build the system prompt once (same for all rounds of this chain)
    system_prompt = build_system_prompt(doc_type, provider_system_prompt, condition)

    for round_num in range(start_round, n_rounds + 1):
        console.print(f"  Round {round_num}/{n_rounds}...", end=" ")

        user_prompt = make_user_prompt(doc_name, doc_type, doc_provider, content, condition)

        try:
            current_prompt = user_prompt
            retried = False
            last_error: Exception | None = None
            usage = {"input_tokens": 0, "output_tokens": 0, "elapsed_ms": 0}

            for attempt in range(1, MAX_EDIT_ATTEMPTS + 1):
                attempt_usage, change_desc, find_text, replace_text, _, attempt_retried = await generate_edit(
                    model=model,
                    system_prompt=system_prompt,
                    user_prompt=current_prompt,
                    temperature=temperature,
                    openrouter_config=openrouter_config,
                )
                usage["input_tokens"] += attempt_usage["input_tokens"]
                usage["output_tokens"] += attempt_usage["output_tokens"]
                usage["elapsed_ms"] += attempt_usage["elapsed_ms"]
                retried = retried or attempt_retried or attempt > 1

                try:
                    if is_no_change_response(find_text, replace_text):
                        diff_result = None
                    else:
                        diff_result = apply_diff(content, find_text, replace_text)
                        ensure_unique_match(diff_result)
                    break
                except ValueError as e:
                    last_error = e
                    if attempt == MAX_EDIT_ATTEMPTS:
                        raise
                    current_prompt = (
                        f"{user_prompt}\n\n"
                        f"{RETRY_PROMPT.format(error=str(e))}\n\n"
                        f"Previous response:\n"
                        f"---CHANGE DESCRIPTION---\n{change_desc}\n\n"
                        f"---FIND---\n{find_text}\n\n"
                        f"---REPLACE---\n{replace_text}"
                    )
            else:
                assert last_error is not None
                raise last_error

            no_change = is_no_change_response(find_text, replace_text)
            new_content = content if no_change else diff_result.new_content

            if (
                not no_change
                and diff_result.match_strategy == "fuzzy"
                and diff_result.fuzzy_score is not None
            ):
                console.print(
                    f"    [yellow]Using fuzzy match[/yellow] "
                    f"(similarity {diff_result.fuzzy_score:.3f})"
                )

            record = EditRecord(
                experiment=experiment_name,
                condition_id=condition_id,
                condition_name=condition_name,
                model_id=model.model_id,
                model_display=model.display_name,
                document_id=doc_id,
                document_provider=doc_provider,
                doc_type=doc_type,
                round_number=round_num,
                total_rounds=n_rounds,
                change_description=change_desc,
                find_text=find_text,
                replace_text=replace_text,
                new_content=new_content,
                input_tokens=usage["input_tokens"],
                output_tokens=usage["output_tokens"],
                elapsed_ms=usage["elapsed_ms"],
                match_strategy="no_change" if no_change else diff_result.match_strategy,
                retried=retried,
                no_change=no_change,
            )

            # Update content for next round
            content = new_content

            console.print(
                f"[green]done[/green] "
                f"({usage['input_tokens']}+{usage['output_tokens']} tokens, "
                f"{usage['elapsed_ms']}ms)"
            )
            if retried:
                console.print("    [yellow]Recovered after retry[/yellow]")
            if no_change:
                console.print("    [yellow]No change selected[/yellow]")
            console.print(f"    Change: {change_desc[:120]}...")

        except Exception as e:
            record = EditRecord(
                experiment=experiment_name,
                condition_id=condition_id,
                condition_name=condition_name,
                model_id=model.model_id,
                model_display=model.display_name,
                document_id=doc_id,
                document_provider=doc_provider,
                doc_type=doc_type,
                round_number=round_num,
                total_rounds=n_rounds,
                change_description="",
                new_content="",
                error=str(e),
            )
            from rich.markup import escape
            console.print(f"[red]error: {escape(str(e))}[/red]")

        append_record(output_path, record)


async def main():
    parser = argparse.ArgumentParser(description="Run iterative edit experiment")
    parser.add_argument("--rounds", type=int, help="Override number of rounds")
    parser.add_argument("--model", type=str, help="Run only one provider (anthropic/openai/google/xai)")
    parser.add_argument("--condition", type=str, help="Run only one condition_id from the config")
    parser.add_argument("--dry-run", action="store_true", help="Print plan without calling APIs")
    parser.add_argument("--config", type=str, default="experiments/iterative_edit/config.yaml")
    args = parser.parse_args()

    config_path = PROJECT_ROOT / args.config
    config = load_config(config_path)

    experiment_name = config["experiment"].get("name", "iterative_edit")
    n_rounds = args.rounds or config["experiment"]["n_rounds"]
    temperature = config["experiment"]["temperature"]
    openrouter_config = config.get("openrouter")
    conditions = [
        normalize_condition(condition)
        for condition in config["experiment"].get("conditions", [{"condition_id": "baseline", "condition_name": "Baseline"}])
    ]
    if args.condition:
        conditions = [condition for condition in conditions if condition["condition_id"] == args.condition]
        if not conditions:
            raise SystemExit(f"Unknown condition_id: {args.condition}")

    # Set up output
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    output_dir = PROJECT_ROOT / "results" / "iterative_edit"
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"run_{timestamp}.jsonl"

    # Check for existing run to resume
    existing_runs = sorted(output_dir.glob("run_*.jsonl"))
    existing_records = []
    if existing_runs:
        latest_run = existing_runs[-1]
        candidate_records = load_records(latest_run, EditRecord)
        latest_experiment = candidate_records[0].experiment if candidate_records else None
        if latest_experiment == experiment_name:
            console.print(f"[yellow]Found existing run: {latest_run.name}[/yellow]")
            output_path = latest_run  # Resume into the same file
            existing_records = candidate_records
            console.print(f"  {len(existing_records)} records loaded")

    # Build assignment list
    assignments = config["assignments"]
    if args.model:
        assignments = [a for a in assignments if a["model"]["provider"] == args.model]

    # Print plan
    table = Table(title=f"Iterative Edit Experiment ({n_rounds} rounds)")
    table.add_column("Model")
    table.add_column("Document")
    table.add_column("Type")
    table.add_column("Condition")
    table.add_column("Status")

    total_calls = 0
    for assignment in assignments:
        model_spec = ModelSpec(**assignment["model"])
        for condition in conditions:
            for doc in assignment["documents"]:
                completed = get_completed_rounds(
                    output_path,
                    model_spec.model_id,
                    doc["doc_id"],
                    condition["condition_id"],
                )
                completed_count = min(len(completed), n_rounds)
                remaining = max(0, n_rounds - completed_count)
                status = f"{completed_count}/{n_rounds} done" if completed_count else "pending"
                table.add_row(
                    model_spec.display_name,
                    doc["name"],
                    doc["doc_type"],
                    condition["condition_name"],
                    status,
                )
                total_calls += remaining

    console.print(table)
    console.print(f"\nTotal API calls needed: {total_calls}")
    console.print(f"Output: {output_path}\n")

    if args.dry_run:
        console.print("[yellow]Dry run -- exiting[/yellow]")
        return

    # Run
    for assignment in assignments:
        model_spec = ModelSpec(**assignment["model"])
        console.rule(f"[bold]{model_spec.display_name}[/bold]")

        # Load this provider's system prompt for constitution edits
        provider = model_spec.provider
        sp_doc_id = PROVIDER_SYSTEM_PROMPTS.get(provider)
        provider_system_prompt = None
        if sp_doc_id:
            try:
                provider_system_prompt = load_processed_document(sp_doc_id)
                console.print(f"  [dim]Loaded {provider} system prompt ({len(provider_system_prompt):,} chars) for constitution edits[/dim]")
            except FileNotFoundError:
                console.print(f"  [yellow]Warning: no processed system prompt for {provider}, constitutions will use edit instruction only[/yellow]")

        for condition in conditions:
            console.print(f"\n[bold]{condition['condition_name']}[/bold]")
            for doc in assignment["documents"]:
                console.print(f"\n[bold]{doc['name']}[/bold] ({doc['doc_type']})")

                await run_edit_chain(
                    experiment_name=experiment_name,
                    condition=condition,
                    model=model_spec,
                    doc_id=doc["doc_id"],
                    doc_name=doc["name"],
                    doc_provider=doc["provider"],
                    doc_type=doc["doc_type"],
                    n_rounds=n_rounds,
                    temperature=temperature,
                    output_path=output_path,
                    existing_records=existing_records,
                    provider_system_prompt=provider_system_prompt,
                    openrouter_config=openrouter_config,
                )

    console.print(f"\n[green]Experiment complete![/green] Results: {output_path}")


if __name__ == "__main__":
    asyncio.run(main())
