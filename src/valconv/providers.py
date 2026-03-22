"""Unified LLM provider using litellm with OpenRouter."""

import os
import time
import warnings

import litellm
from dotenv import load_dotenv
from tenacity import retry, stop_after_attempt, wait_exponential

from .models import ModelSpec

load_dotenv()

# Configure litellm for OpenRouter
litellm.drop_params = True
litellm.suppress_debug_info = True
import logging
logging.getLogger("LiteLLM").setLevel(logging.CRITICAL)
warnings.filterwarnings(
    "ignore",
    message=r"Pydantic serializer warnings:",
    category=UserWarning,
)


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
) -> dict:
    """Make an async LLM API call via litellm/OpenRouter.

    Returns dict with keys: text, input_tokens, output_tokens, elapsed_ms.
    """
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]

    start = time.monotonic()
    # Prefix with openrouter/ so litellm routes correctly
    model_id = model.model_id
    if not model_id.startswith("openrouter/"):
        model_id = f"openrouter/{model_id}"

    response = await litellm.acompletion(
        model=model_id,
        messages=messages,
        max_tokens=max_tokens,
        temperature=temperature,
        api_key=os.getenv("OPENROUTER_API_KEY"),
    )
    elapsed = int((time.monotonic() - start) * 1000)

    return {
        "text": response.choices[0].message.content,
        "input_tokens": response.usage.prompt_tokens,
        "output_tokens": response.usage.completion_tokens,
        "elapsed_ms": elapsed,
    }
