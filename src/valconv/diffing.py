"""Utilities for applying model-proposed find/replace diffs."""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from difflib import SequenceMatcher


_WHITESPACE_RE = re.compile(r"\S+")
_STRIP_PUNCT = ".,;:!?\"'`()[]{}"


@dataclass(frozen=True)
class TokenSpan:
    token: str
    start: int
    end: int


@dataclass(frozen=True)
class DiffApplyResult:
    new_content: str
    match_strategy: str
    match_count: int = 1
    fuzzy_score: float | None = None


@dataclass(frozen=True)
class MatchSpan:
    start: int
    end: int
    match_strategy: str
    match_count: int = 1
    fuzzy_score: float | None = None


def _tokenize_with_spans(text: str) -> list[TokenSpan]:
    return [
        TokenSpan(token=match.group(0), start=match.start(), end=match.end())
        for match in _WHITESPACE_RE.finditer(text)
    ]


def _replace_span(content: str, start: int, end: int, replace_text: str) -> str:
    return content[:start] + replace_text + content[end:]


def _normalize_token(token: str) -> str:
    return token.strip(_STRIP_PUNCT).lower()


def _find_exact_match(content: str, find_text: str) -> MatchSpan | None:
    start = content.find(find_text)
    if start == -1:
        return None

    return MatchSpan(
        start=start,
        end=start + len(find_text),
        match_strategy="exact",
        match_count=content.count(find_text),
    )


def _find_whitespace_insensitive_match(content: str, find_text: str) -> MatchSpan | None:
    content_tokens = _tokenize_with_spans(content)
    find_tokens = [token.token for token in _tokenize_with_spans(find_text)]

    if not content_tokens or not find_tokens or len(find_tokens) > len(content_tokens):
        return None

    matches: list[tuple[int, int]] = []
    target_len = len(find_tokens)
    for start_idx in range(len(content_tokens) - target_len + 1):
        window = content_tokens[start_idx:start_idx + target_len]
        if [token.token for token in window] == find_tokens:
            matches.append((window[0].start, window[-1].end))

    if not matches:
        return None

    start, end = matches[0]
    return MatchSpan(
        start=start,
        end=end,
        match_strategy="whitespace",
        match_count=len(matches),
    )


def _fuzzy_score(a: str, b: str) -> float:
    return SequenceMatcher(None, a, b).ratio()


def _find_fuzzy_match(
    content: str,
    find_text: str,
    *,
    min_score: float = 0.92,
    ambiguity_gap: float = 0.015,
) -> MatchSpan | None:
    content_tokens = _tokenize_with_spans(content)
    find_tokens = _tokenize_with_spans(find_text)

    if len(find_tokens) < 4 or len(content_tokens) < len(find_tokens):
        return None

    target_len = len(find_tokens)
    target_text = " ".join(token.token for token in find_tokens)
    target_start = _normalize_token(find_tokens[0].token)
    target_end = _normalize_token(find_tokens[-1].token)
    max_delta = max(2, math.ceil(target_len * 0.2))

    candidates: list[tuple[float, int, int, int, int]] = []
    min_window = max(1, target_len - max_delta)
    max_window = min(len(content_tokens), target_len + max_delta)

    for window_len in range(min_window, max_window + 1):
        for start_idx in range(len(content_tokens) - window_len + 1):
            end_idx = start_idx + window_len
            window = content_tokens[start_idx:end_idx]
            if _normalize_token(window[0].token) != target_start:
                continue
            if _normalize_token(window[-1].token) != target_end:
                continue
            candidate_text = " ".join(token.token for token in window)
            score = _fuzzy_score(candidate_text, target_text)
            if score >= min_score:
                span_start = window[0].start
                span_end = window[-1].end
                candidates.append((score, start_idx, end_idx, span_start, span_end))

    if not candidates:
        return None

    candidates.sort(key=lambda item: (-item[0], item[1], item[2]))
    best_score, _, _, best_start, best_end = candidates[0]

    distinct_near_best = [
        candidate for candidate in candidates[1:]
        if candidate[3] != best_start and candidate[4] != best_end and best_score - candidate[0] < ambiguity_gap
    ]
    if distinct_near_best:
        raise ValueError(
            "Fuzzy match is ambiguous; multiple similar passages found. "
            f"Best score={best_score:.3f}"
        )

    return MatchSpan(
        start=best_start,
        end=best_end,
        match_strategy="fuzzy",
        fuzzy_score=best_score,
    )


def apply_diff(content: str, find_text: str, replace_text: str) -> DiffApplyResult:
    """Apply a model-proposed find/replace diff with conservative fallbacks."""
    if not find_text.strip():
        raise ValueError("FIND text is empty")

    match = _find_exact_match(content, find_text)
    if match is None:
        match = _find_whitespace_insensitive_match(content, find_text)
    if match is None:
        match = _find_fuzzy_match(content, find_text)
    if match is not None:
        return DiffApplyResult(
            new_content=_replace_span(content, match.start, match.end, replace_text),
            match_strategy=match.match_strategy,
            match_count=match.match_count,
            fuzzy_score=match.fuzzy_score,
        )

    raise ValueError(
        "FIND text not found in document, even with whitespace-insensitive and fuzzy matching. "
        f"First 100 chars of FIND: {find_text[:100]!r}"
    )
