# Plan (Phase 1b-e AI import resolver):
# - Single generic resolver for all import types; no import-type-specific branches.
# - Every public entry checks Settings.ai_assist_enabled before any API call.
# - Anthropic client lazy-imported; failures log and return None (never raise).

from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass, field
from typing import Any

from app.core.config import get_settings

logger = logging.getLogger(__name__)

AI_AUTO_RESOLVE_THRESHOLD = 0.90
_MODEL = "claude-sonnet-4-20250514"
_MAX_TOKENS = 1000


@dataclass
class ColumnMappingSuggestion:
    mappings: dict[str, str]
    confidence: float
    unmapped: list[str]
    notes: str
    ai_generated: bool = True


@dataclass
class TokenResolutionSuggestion:
    best_match_id: int | None
    confidence: float
    reasoning: str
    alternatives: list[dict[str, Any]]
    ai_generated: bool = True


@dataclass
class FormatDriftResult:
    has_drift: bool
    new_columns: list[str]
    missing_columns: list[str]
    confidence: float
    suggested_updated_mapping: dict[str, str] | None


def _ai_enabled() -> bool:
    return bool(get_settings().ai_assist_enabled)


def _anthropic_client():
    if not _ai_enabled():
        return None
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        logger.warning("AI assist enabled but ANTHROPIC_API_KEY is not set")
        return None
    try:
        import anthropic  # type: ignore[import-untyped]
    except ImportError:
        logger.warning("AI assist enabled but anthropic package is not installed")
        return None
    return anthropic.Anthropic(api_key=api_key)


def _extract_json_object(text: str) -> dict[str, Any] | None:
    text = (text or "").strip()
    if not text:
        return None
    try:
        parsed = json.loads(text)
        return parsed if isinstance(parsed, dict) else None
    except json.JSONDecodeError:
        pass
    m = re.search(r"\{[\s\S]*\}", text)
    if not m:
        return None
    try:
        parsed = json.loads(m.group(0))
        return parsed if isinstance(parsed, dict) else None
    except json.JSONDecodeError:
        return None


def _call_claude(*, system: str, user: str) -> dict[str, Any] | None:
    client = _anthropic_client()
    if client is None:
        return None
    try:
        msg = client.messages.create(
            model=_MODEL,
            max_tokens=_MAX_TOKENS,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        parts = []
        for block in msg.content:
            if getattr(block, "type", None) == "text":
                parts.append(getattr(block, "text", "") or "")
        return _extract_json_object("".join(parts))
    except Exception as exc:  # noqa: BLE001
        logger.warning("AI import resolver API call failed: %s", exc)
        return None


def suggest_column_mapping(
    headers: list[str],
    sample_rows: list[dict],
    canonical_fields: list[str],
    existing_mapping: dict | None = None,
) -> ColumnMappingSuggestion | None:
    if not _ai_enabled():
        return None

    user = (
        f"Headers: {headers}\n"
        f"Sample rows: {sample_rows[:3]}\n"
        f"Canonical fields: {canonical_fields}\n"
        f"Existing mapping hint: {existing_mapping}\n"
        "Return JSON: {\n"
        "  'mappings': {'source_col': 'canonical_field'},\n"
        "  'confidence': 0.0-1.0,\n"
        "  'unmapped': ['cols that could not be mapped'],\n"
        "  'notes': 'brief explanation'\n"
        "}"
    )
    data = _call_claude(
        system=(
            "You are a data mapping assistant for a supply chain platform. "
            "Map source column headers to canonical field names. Return JSON only, no other text."
        ),
        user=user,
    )
    if not data:
        return None

    mappings_raw = data.get("mappings")
    mappings: dict[str, str] = {}
    if isinstance(mappings_raw, dict):
        for k, v in mappings_raw.items():
            if isinstance(k, str) and isinstance(v, str) and k.strip() and v.strip():
                mappings[k.strip()] = v.strip()

    try:
        confidence = float(data.get("confidence", 0.0))
    except (TypeError, ValueError):
        confidence = 0.0

    unmapped = data.get("unmapped")
    unmapped_list = [str(x) for x in unmapped] if isinstance(unmapped, list) else []

    notes = str(data.get("notes") or "")
    return ColumnMappingSuggestion(
        mappings=mappings,
        confidence=confidence,
        unmapped=unmapped_list,
        notes=notes,
        ai_generated=True,
    )


def suggest_token_resolution(
    raw_token: str,
    token_type: str,
    candidates: list[dict],
    context: dict | None = None,
) -> TokenResolutionSuggestion | None:
    if not _ai_enabled():
        return None

    user = (
        f"Raw token: {raw_token}\n"
        f"Token type: {token_type}\n"
        f"Candidate records: {candidates[:10]}\n"
        f"Context: {context}\n"
        "Return JSON: {\n"
        "  'best_match_id': int | null,\n"
        "  'confidence': 0.0-1.0,\n"
        "  'reasoning': 'brief explanation',\n"
        "  'alternatives': [{'id': int, 'confidence': float}]\n"
        "}"
    )
    data = _call_claude(
        system=(
            "You are a data resolution assistant for a supply chain platform. "
            "Match a raw token to the most likely master record. Return JSON only."
        ),
        user=user,
    )
    if not data:
        return None

    best_id = data.get("best_match_id")
    try:
        best_match_id = int(best_id) if best_id is not None else None
    except (TypeError, ValueError):
        best_match_id = None

    try:
        confidence = float(data.get("confidence", 0.0))
    except (TypeError, ValueError):
        confidence = 0.0

    reasoning = str(data.get("reasoning") or "")
    alts = data.get("alternatives")
    alternatives = [a for a in alts if isinstance(a, dict)] if isinstance(alts, list) else []

    return TokenResolutionSuggestion(
        best_match_id=best_match_id,
        confidence=confidence,
        reasoning=reasoning,
        alternatives=alternatives,
        ai_generated=True,
    )


def _headers_from_stored_mapping(stored_mapping: dict) -> list[str]:
    if not stored_mapping:
        return []
    bh = stored_mapping.get("by_header_norm")
    if isinstance(bh, dict):
        return list(bh.keys())
    if isinstance(stored_mapping.get("headers"), list):
        return [str(h) for h in stored_mapping["headers"]]
    return []


def detect_format_drift(
    current_headers: list[str],
    stored_headers: list[str],
    stored_mapping: dict,
) -> FormatDriftResult | None:
    cur = {str(h).strip().lower() for h in current_headers if h}
    stored = {str(h).strip().lower() for h in stored_headers if h}
    if not stored and stored_mapping:
        stored = {str(h).strip().lower() for h in _headers_from_stored_mapping(stored_mapping)}

    new_columns = sorted(cur - stored)
    missing_columns = sorted(stored - cur)
    has_drift = bool(new_columns or missing_columns)

    if not has_drift:
        return FormatDriftResult(
            has_drift=False,
            new_columns=[],
            missing_columns=[],
            confidence=1.0,
            suggested_updated_mapping=None,
        )

    partial_overlap = bool(cur & stored)
    if not _ai_enabled() or not partial_overlap:
        return FormatDriftResult(
            has_drift=True,
            new_columns=new_columns,
            missing_columns=missing_columns,
            confidence=1.0 if not partial_overlap else 0.7,
            suggested_updated_mapping=None,
        )

    suggestion = suggest_column_mapping(
        headers=list(current_headers),
        sample_rows=[],
        canonical_fields=[],
        existing_mapping=stored_mapping,
    )
    suggested: dict[str, str] | None = None
    conf = 0.7
    if suggestion and suggestion.mappings:
        suggested = dict(suggestion.mappings)
        conf = float(suggestion.confidence)

    return FormatDriftResult(
        has_drift=True,
        new_columns=new_columns,
        missing_columns=missing_columns,
        confidence=conf,
        suggested_updated_mapping=suggested,
    )
