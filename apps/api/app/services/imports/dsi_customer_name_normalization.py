"""Customer/dealer display-name normalisation for DSI duplicate detection and matching."""

from __future__ import annotations

import re

# Legal / trading suffixes and noise (order: longer phrases first).
_LEGAL_SUFFIX_PATTERNS: tuple[re.Pattern[str], ...] = tuple(
    re.compile(p, re.IGNORECASE)
    for p in (
        r"\(\s*pty\s*\)\s*ltd\.?",
        r"\(\s*pty\s*\)",
        r"\bpty\.?\s*ltd\.?",
        r"\bproprietary\s+limited\b",
        r"\bclose\s+corporation\b",
        r"\bn\.?p\.?c\.?\b",
        r"\bincorporated\b",
        r"\blimited\b",
        r"\bcompany\b",
        r"\bcorp\.?\b",
        r"\binc\.?\b",
        r"\bltd\.?\b",
        r"\bllc\.?\b",
        r"\bnpc\b",
        r"\bcc\b",
    )
)

_TRADING_AS = re.compile(
    r"\b(?:t/a|a/t|trading\s+as|ta:)\s+",
    re.IGNORECASE,
)


def normalize_customer_name_for_similarity(raw: str | None) -> str:
    """Strip legal suffixes and noise, lowercase, collapse whitespace — for duplicate/compare only."""
    s = (raw or "").strip()
    if not s:
        return ""
    s = _TRADING_AS.sub(" ", s)
    for pat in _LEGAL_SUFFIX_PATTERNS:
        s = pat.sub(" ", s)
    s = re.sub(r"[,;]+", " ", s)
    s = re.sub(r"[.()]+", " ", s)
    s = re.sub(r"\s+", " ", s).strip().lower()
    return s


def normalize_customer_name_token(raw: str | None) -> str:
    """Normalised token stored on candidate context for downstream matching (may be empty)."""
    return normalize_customer_name_for_similarity(raw)
