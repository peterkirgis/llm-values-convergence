"""Unified LLM provider using OpenAI client pointed at OpenRouter."""

from __future__ import annotations

import os
import time

from dotenv import load_dotenv
from openai import AsyncOpenAI
from tenacity import retry, stop_after_attempt, wait_exponential

from .models import ModelSpec

load_dotenv()

_client: AsyncOpenAI | None = None


def _get_client() -> AsyncOpenAI:
    global _client
    if _client is None:
        _client = AsyncOpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=os.getenv("OPENROUTER_API_KEY"),
        )
    return _client


def _build_extra_body(
    model: ModelSpec,
    openrouter_config: dict | None,
) -> dict:
    """Build the extra_body dict for OpenRouter-specific parameters."""
    if not openrouter_config:
        return {}

    extra: dict = {}

    # Provider pinning
    provider_block: dict = {}
    provider_order_map = openrouter_config.get("provider_order", {})
    order = provider_order_map.get(model.provider)
    if order:
        provider_block["order"] = order
    if "allow_fallbacks" in openrouter_config:
        provider_block["allow_fallbacks"] = openrouter_config["allow_fallbacks"]
    if provider_block:
        extra["provider"] = provider_block

    # Compression control
    if openrouter_config.get("disable_compression"):
        extra["plugins"] = [{"id": "context-compression", "enabled": False}]

    return extra


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=2, min=4, max=60),
)
async def call_llm(
    model: ModelSpec,
    system_prompt: str,
    user_prompt: str,
    temperature: float = 0.7,
    max_tokens: int = 8192,
    openrouter_config: dict | None = None,
) -> dict:
    """Make an async LLM API call via OpenRouter.

    Returns dict with keys: text, input_tokens, output_tokens, elapsed_ms.
    """
    client = _get_client()
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]

    extra_body = _build_extra_body(model, openrouter_config)

    start = time.monotonic()
    response = await client.chat.completions.create(
        model=model.model_id,
        messages=messages,
        max_tokens=max_tokens,
        temperature=temperature,
        extra_body=extra_body if extra_body else None,
    )
    elapsed = int((time.monotonic() - start) * 1000)

    return {
        "text": response.choices[0].message.content,
        "input_tokens": response.usage.prompt_tokens,
        "output_tokens": response.usage.completion_tokens,
        "elapsed_ms": elapsed,
    }
