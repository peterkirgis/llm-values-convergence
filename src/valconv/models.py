"""Pydantic data models for the values convergence experiments."""

from datetime import datetime, timezone
from typing import Optional

from pydantic import BaseModel, Field


class ModelSpec(BaseModel):
    """Specification for a model to use in experiments."""
    model_id: str          # OpenRouter model ID, e.g. "anthropic/claude-opus-4-6"
    provider: str          # "anthropic", "openai", "google", "xai"
    display_name: str
    # Optional reasoning effort for reasoning-capable models. OpenRouter accepts
    # `reasoning: {effort: "minimal"|"low"|"medium"|"high"}` in the request body
    # for models that support it. Leave None to let the provider apply its
    # default (which is "adaptive" / "high" for most thinking models).
    reasoning_effort: Optional[str] = None


class DocumentInfo(BaseModel):
    """Metadata about a document used in experiments."""
    doc_id: str
    name: str
    provider: str          # Which provider this document belongs to
    doc_type: str          # "constitution" or "system_prompt"
    char_count: int = 0


class EditRecord(BaseModel):
    """Record of a single iterative edit."""
    experiment: str = "iterative_edit"
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    condition_id: str = "baseline"
    condition_name: str = "Baseline"
    model_id: str
    model_display: str
    document_id: str
    document_provider: str
    doc_type: str
    round_number: int
    total_rounds: int
    change_description: str    # The model's description of what it changed
    find_text: str = ""        # The text the model wanted to replace
    replace_text: str = ""     # The replacement text
    new_content: str           # The full document after applying the edit
    input_tokens: int = 0
    output_tokens: int = 0
    elapsed_ms: int = 0
    match_strategy: str = "exact"  # "exact", "whitespace", "fuzzy"
    retried: bool = False
    no_change: bool = False
    error: Optional[str] = None
