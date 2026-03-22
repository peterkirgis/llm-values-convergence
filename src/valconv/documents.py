"""Document loading, cleaning, and preprocessing."""

import re
from pathlib import Path


def clean_pandoc_markdown(text: str) -> str:
    """Strip pandoc CSS class annotations from markdown.

    Handles patterns like:
      [text]{.CharOverride-7 .paragraph-style}
      ::: {#id .class role="doc-pagebreak"}
      :::
      :::: _idGenObjectLayout-1
    """
    # Remove span-level class annotations: [text]{.class1 .class2}
    # But preserve link syntax: [text](url)
    text = re.sub(r'\[([^\]]*)\]\{[^}]*\}', r'\1', text)
    # Remove div-level pandoc fenced divs
    text = re.sub(r'^:{2,}\s*\{[^}]*\}\s*$', '', text, flags=re.MULTILINE)
    text = re.sub(r'^:{2,}\s*\S+\s*$', '', text, flags=re.MULTILINE)
    text = re.sub(r'^:{2,}\s*$', '', text, flags=re.MULTILINE)
    # Remove image references to base64 data
    text = re.sub(r'!\[[^\]]*\]\(data:image/[^)]+\)', '', text)
    # Remove other image references (e.g. local images)
    text = re.sub(r'!\[[^\]]*\]\(image/[^)]+\)', '', text)
    # Clean up excessive whitespace
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()


def clean_openai_spec(text: str) -> str:
    """Clean the OpenAI model spec which has HTML/pandoc hybrid markup."""
    # First apply pandoc cleaning
    text = clean_pandoc_markdown(text)
    # Find where the actual content starts (# Overview)
    overview_match = re.search(r'^# Overview', text, re.MULTILINE)
    if overview_match:
        text = text[overview_match.start():]
    # Remove any remaining HTML tags
    text = re.sub(r'<[^>]+>', '', text)
    # Remove base64 remnants
    text = re.sub(r'PHN2Z[A-Za-z0-9+/=]+', '', text)
    # Remove lines that are just colons (pandoc div remnants)
    text = re.sub(r'^:+\s*$', '', text, flags=re.MULTILINE)
    # Remove {#anchor .class} annotations on headers
    text = re.sub(r'\{#[^}]*\}', '', text)
    # Remove authority sidebar badges like [Root], [System], etc. in isolation
    text = re.sub(r'\[(?:Root|System|Developer|User|Guideline)\]', '', text)
    # Remove +N badges
    text = re.sub(r'\[\+\d+\]', '', text)
    # Clean up lines of just whitespace
    text = re.sub(r'\n{3,}', '\n\n', text)
    # Remove the "functions" and "imports" code sections near the end
    functions_match = re.search(r'^# functions\b', text, re.MULTILINE)
    if functions_match:
        # Keep everything before "# functions"
        imports_match = re.search(r'^# \[\.\.\.] imports', text, re.MULTILINE)
        end_cut = functions_match.start()
        if imports_match and imports_match.start() < functions_match.start():
            end_cut = imports_match.start()
        # Find the next real section after the code
        next_section = re.search(r'^# (?!functions|\.)', text[functions_match.end():], re.MULTILINE)
        if next_section:
            text = text[:end_cut] + text[functions_match.end() + next_section.start():]
        else:
            text = text[:end_cut]
    return text.strip()


def strip_operational_sections(text: str, doc_id: str) -> str:
    """Remove tool API definitions and operational noise from system prompts.

    Keeps behavioral instructions, identity, values, and style guidance.
    Only strips tool namespace definitions (pure API specs) and file handling noise.
    """
    if doc_id == "opus_system_prompt":
        # Remove bracketed sections that are about tools/skills/files
        for tag in [
            "computer_use", "skills", "file_creation_advice",
            "unnecessary_computer_use_avoidance",
            "high_level_computer_use_explanation",
            "file_handling_rules", "producing_outputs",
            "sharing_files", "artifacts", "notes_on_user_uploaded_files",
            "available_skills", "network_configuration",
            "filesystem_configuration",
        ]:
            text = re.sub(
                rf'\[{tag}\].*?\[/{tag}\]',
                '', text, flags=re.DOTALL | re.IGNORECASE,
            )
    elif doc_id == "gpt_system_prompt":
        # The GPT prompt is mostly tool namespace definitions.
        # Keep: identity, trustworthiness, writing style, safety notes, behavior
        # Remove: # Artifacts, Skill Invocation Rules, ## Namespace: * blocks,
        #         tool definitions, code blocks with API specs
        # Remove the Artifacts section (UI-only)
        text = re.sub(
            r'^# Artifacts\n.*?(?=^## Trustworthiness|^## Writing Style|^---|\Z)',
            '', text, flags=re.DOTALL | re.MULTILINE,
        )
        # Remove Skill Invocation Rules
        text = re.sub(
            r'^Skill Invocation Rules\n.*?(?=^## Writing Style|^## Tips|^---|\Z)',
            '', text, flags=re.DOTALL | re.MULTILINE,
        )
        # Remove Writing blocks section (UI-only)
        text = re.sub(
            r'^## Writing blocks.*?(?=^## Tips|^## Writing Style|^---|\Z)',
            '', text, flags=re.DOTALL | re.MULTILINE,
        )
        # Remove ad-related paragraphs
        text = re.sub(
            r'^If the user asks (?:whether advertisers|if they will see ads|don\'t show me ads).*?\n\n',
            '', text, flags=re.DOTALL | re.MULTILINE,
        )
        # Remove all ## Namespace: * sections (tool API definitions)
        text = re.sub(
            r'^## Namespace:.*?(?=^## (?!Namespace)|^# |\Z)',
            '', text, flags=re.DOTALL | re.MULTILINE,
        )
        # Remove # Tools header and description
        text = re.sub(
            r'^# Tools\n.*?(?=^## |^# |\Z)',
            '', text, flags=re.DOTALL | re.MULTILINE,
        )
        # Remove code blocks (tool schemas, deprecated dev messages)
        text = re.sub(r'^```.*?^```', '', text, flags=re.DOTALL | re.MULTILINE)
        text = re.sub(r'^````.*?^````', '', text, flags=re.DOTALL | re.MULTILINE)
        # Remove "# Valid channels" line
        text = re.sub(r'^# Valid channels.*$', '', text, flags=re.MULTILINE)
        # Remove "# Juice" line
        text = re.sub(r'^# Juice.*$', '', text, flags=re.MULTILINE)
        # Remove "# Desired oververbosity" and its explanation
        text = re.sub(
            r'^# Desired oververbosity.*?(?=^# |^## |\Z)',
            '', text, flags=re.DOTALL | re.MULTILINE,
        )
        # Remove File Search Tool sections
        text = re.sub(
            r'^# File Search Tool.*?(?=^# (?!File Search)|\Z)',
            '', text, flags=re.DOTALL | re.MULTILINE,
        )
        # Remove Deprecated developer message section
        text = re.sub(
            r'^## Deprecated developer message.*?(?=^## (?!Deprecated)|^# |\Z)',
            '', text, flags=re.DOTALL | re.MULTILINE,
        )
        # Remove Rich UI elements section
        text = re.sub(
            r'^## Rich UI elements.*?(?=^## (?!Rich)|^# |\Z)',
            '', text, flags=re.DOTALL | re.MULTILINE,
        )
    elif doc_id == "gemini_system_prompt":
        # Remove capability info block (image/video/music tools, Gemini Live)
        cap_start = text.find("The following information block is strictly")
        if cap_start > 0:
            cap_end = text.find("Response Guiding Principles", cap_start)
            if cap_end > 0:
                text = text[:cap_start] + text[cap_end:]
    # grok_system_prompt: keep everything, it's compact and values-relevant
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()


def load_and_clean(raw_path: Path, doc_id: str) -> str:
    """Load a raw document and return cleaned content."""
    text = raw_path.read_text(encoding="utf-8")

    if doc_id == "openai_model_spec":
        return clean_openai_spec(text)
    elif doc_id == "claude_constitution":
        return clean_pandoc_markdown(text)
    else:
        return text


def process_all_documents(base_dir: Path) -> dict[str, Path]:
    """Process all raw documents and write cleaned versions to data/processed/."""
    processed_dir = base_dir / "data" / "processed"
    processed_dir.mkdir(parents=True, exist_ok=True)

    # Document definitions: (doc_id, raw_path, is_system_prompt)
    documents = [
        ("claude_constitution", base_dir / "constitutions" / "claudes-constitution.md", False),
        ("gemini_constitution", base_dir / "constitutions" / "gemini.md", False),
        ("openai_model_spec", base_dir / "constitutions" / "openai_model_spec.md", False),
        ("opus_system_prompt", base_dir / "system_prompts" / "opus_4_6.md", True),
        ("gpt_system_prompt", base_dir / "system_prompts" / "gpt_5_4_thinking.md", True),
        ("gemini_system_prompt", base_dir / "system_prompts" / "gemini_3_1_pro.md", True),
        ("grok_system_prompt", base_dir / "system_prompts" / "grok_4.md", True),
    ]

    results = {}
    for doc_id, raw_path, is_system_prompt in documents:
        content = load_and_clean(raw_path, doc_id)
        if is_system_prompt:
            content = strip_operational_sections(content, doc_id)
        out_path = processed_dir / f"{doc_id}.md"
        out_path.write_text(content, encoding="utf-8")
        results[doc_id] = out_path
        line_count = content.count('\n') + 1
        char_count = len(content)
        print(f"  {doc_id}: {line_count:,} lines, {char_count:,} chars -> {out_path.name}")

    return results


if __name__ == "__main__":
    base = Path(__file__).resolve().parent.parent.parent
    print(f"Processing documents from {base}")
    process_all_documents(base)
    print("Done.")
