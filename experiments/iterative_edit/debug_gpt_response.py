"""Reproduce a GPT-5.4 Mini cross-edit call and print the raw response.

Used to diagnose why GPT keeps producing responses that miss the
---CHANGE DESCRIPTION---/---FIND---/---REPLACE--- delimiters when editing
foreign documents.

Usage:
    python experiments/iterative_edit/debug_gpt_response.py
    python experiments/iterative_edit/debug_gpt_response.py --doc grok_system_prompt
    python experiments/iterative_edit/debug_gpt_response.py --doc openai_model_spec --rounds 2
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))
sys.path.insert(0, str(PROJECT_ROOT / "experiments" / "iterative_edit"))

from valconv.models import ModelSpec
from valconv.providers import call_llm
from prompts import build_system_prompt, make_user_prompt, normalize_condition

DOC_TYPES = {
    "claude_constitution": "constitution",
    "openai_model_spec": "constitution",
    "gemini_system_prompt": "system_prompt",
    "grok_system_prompt": "system_prompt",
}

DOC_NAMES = {
    "claude_constitution": "Claude's Constitution",
    "openai_model_spec": "OpenAI Model Spec",
    "gemini_system_prompt": "Gemini 3 Flash System Prompt",
    "grok_system_prompt": "Grok 4.2 System Prompt",
}

DOC_PROVIDERS = {
    "claude_constitution": "anthropic",
    "openai_model_spec": "openai",
    "gemini_system_prompt": "google",
    "grok_system_prompt": "xai",
}


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--doc",
        default="gemini_system_prompt",
        choices=sorted(DOC_TYPES.keys()),
        help="Which document to feed to the editor (default: gemini_system_prompt, which failed 3/3)",
    )
    parser.add_argument(
        "--model-id",
        default="openai/gpt-5.4-mini",
        help="OpenRouter model id (default: openai/gpt-5.4-mini)",
    )
    parser.add_argument("--temperature", type=float, default=0.7)
    parser.add_argument("--n", type=int, default=1, help="Number of runs to sample (default 1)")
    parser.add_argument("--quiet", action="store_true", help="Only print per-run status + final summary (skip full response bodies)")
    parser.add_argument("--max-tokens", type=int, default=8192, help="max_tokens to pass to the provider (default 8192, matching run.py)")
    args = parser.parse_args()

    doc_id = args.doc
    doc_type = DOC_TYPES[doc_id]
    doc_name = DOC_NAMES[doc_id]
    doc_provider = DOC_PROVIDERS[doc_id]

    doc_path = PROJECT_ROOT / "data" / "processed" / f"{doc_id}.md"
    content = doc_path.read_text(encoding="utf-8")

    condition = normalize_condition(
        {
            "condition_id": "cross_edit",
            "condition_name": "Cross Edit",
            "prepend_system_prompt_for_constitutions": False,
        }
    )

    system_prompt = build_system_prompt(doc_type, None, condition)
    user_prompt = make_user_prompt(doc_name, doc_type, doc_provider, content, condition)

    print(f"=== Calling {args.model_id} on {doc_id} (doc_type={doc_type}) ===")
    print(f"system_prompt length: {len(system_prompt):,} chars")
    print(f"user_prompt length:   {len(user_prompt):,} chars")
    print()

    model = ModelSpec(
        model_id=args.model_id,
        provider="openai" if args.model_id.startswith("openai/") else args.model_id.split("/")[0],
        display_name=args.model_id.split("/", 1)[-1],
    )

    openrouter_config = {
        "disable_compression": True,
        "allow_fallbacks": False,
        "provider_order": {
            "anthropic": ["anthropic"],
            "openai": ["openai"],
            "google": ["google-ai-studio", "google-vertex"],
            "xai": ["xai"],
        },
    }

    successes = 0
    failures: list[dict] = []

    for i in range(1, args.n + 1):
        result = await call_llm(
            model=model,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            temperature=args.temperature,
            max_tokens=args.max_tokens,
            openrouter_config=openrouter_config,
        )

        text = result["text"]
        has_desc = "---CHANGE DESCRIPTION---" in text
        has_find = "---FIND---" in text
        has_replace = "---REPLACE---" in text
        all_present = has_desc and has_find and has_replace
        status = "PASS" if all_present else "FAIL"
        if all_present:
            successes += 1
        else:
            failures.append(
                {
                    "run": i,
                    "text": text,
                    "has_desc": has_desc,
                    "has_find": has_find,
                    "has_replace": has_replace,
                    "input_tokens": result["input_tokens"],
                    "output_tokens": result["output_tokens"],
                }
            )

        marker = f"[{i}/{args.n}]"
        print(
            f"{marker} {status} "
            f"finish={result.get('finish_reason')} "
            f"in={result['input_tokens']} out={result['output_tokens']} "
            f"delims=desc:{'Y' if has_desc else 'N'}/find:{'Y' if has_find else 'N'}/repl:{'Y' if has_replace else 'N'} "
            f"elapsed={result['elapsed_ms']}ms len={len(text)}"
        )

        if not args.quiet and args.n == 1:
            print()
            print("=== RAW RESPONSE TEXT ===")
            print(text)

    print()
    print("=== SUMMARY ===")
    print(f"{successes}/{args.n} passed the delimiter check ({100 * successes / args.n:.0f}%)")

    if failures:
        print()
        print("=== FAILED RESPONSES (truncated to first 2000 chars each) ===")
        for f in failures:
            print(f"\n--- Run #{f['run']} (out_tokens={f['output_tokens']}, len={len(f['text'])}) ---")
            print(f"  missing: "
                  + ", ".join(
                      name
                      for name, present in [
                          ("---CHANGE DESCRIPTION---", f["has_desc"]),
                          ("---FIND---", f["has_find"]),
                          ("---REPLACE---", f["has_replace"]),
                      ]
                      if not present
                  ))
            print()
            print(f["text"][:2000] if f["text"] else "(empty response)")


if __name__ == "__main__":
    asyncio.run(main())
