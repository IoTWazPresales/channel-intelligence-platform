"""Deterministic competitor mapping scores with explainable factors."""

from __future__ import annotations

from dataclasses import dataclass
import re


@dataclass(frozen=True)
class InternalProductProfile:
    title: str
    category: str | None
    form_factor: str | None
    spec_tokens: list[str]
    internal_price: float | None


@dataclass(frozen=True)
class CompetitorCandidate:
    title: str
    category: str | None
    form_factor: str | None
    spec_tokens: list[str]
    competitor_price: float | None


@dataclass(frozen=True)
class CompetitorMatchResult:
    score: float
    explanation: str
    factors: dict


def _tokenize(text: str) -> set[str]:
    return {t for t in re.split(r"[^a-z0-9]+", text.lower()) if len(t) > 2}


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    inter = len(a & b)
    union = len(a | b)
    return inter / union if union else 0.0


def _category_match(a: str | None, b: str | None) -> float:
    if not a or not b:
        return 0.5
    return 1.0 if a.strip().lower() == b.strip().lower() else 0.0


def _form_match(a: str | None, b: str | None) -> float:
    if not a or not b:
        return 0.5
    return 1.0 if a.strip().lower() == b.strip().lower() else 0.0


def _price_band_proximity(p1: float | None, p2: float | None) -> float:
    if not p1 or not p2 or p1 <= 0 or p2 <= 0:
        return 0.5
    ratio = min(p1, p2) / max(p1, p2)
    return float(ratio)


def score_competitor_candidate(
    internal: InternalProductProfile, candidate: CompetitorCandidate
) -> CompetitorMatchResult:
    cat = _category_match(internal.category, candidate.category)
    form = _form_match(internal.form_factor, candidate.form_factor)
    spec_sim = _jaccard(set(internal.spec_tokens), set(candidate.spec_tokens))
    text_sim = _jaccard(_tokenize(internal.title), _tokenize(candidate.title))
    price_sim = _price_band_proximity(internal.internal_price, candidate.competitor_price)

    score = (
        0.25 * cat
        + 0.15 * form
        + 0.25 * spec_sim
        + 0.25 * text_sim
        + 0.10 * price_sim
    )

    factors = {
        "category_match": cat,
        "form_factor_match": form,
        "spec_similarity": spec_sim,
        "text_similarity": text_sim,
        "price_proximity": price_sim,
    }
    explanation = (
        f"Weighted blend: category {cat:.2f}, form {form:.2f}, specs {spec_sim:.2f}, "
        f"title tokens {text_sim:.2f}, price proximity {price_sim:.2f} → score {score:.3f}."
    )
    return CompetitorMatchResult(score=round(score, 4), explanation=explanation, factors=factors)
