"""Deterministic product token identity keys for DSI resolution and shipment corroboration.

Derives strict OEM sales-model codes embedded in long distributor tokens (e.g. ASUS
``B1502CVA-I58512B9X`` inside a prose ``ModelName``). Lookup keys are used for PM
tier matching and shipment evidence only — ``ImportEntityMappingCandidate.normalized_key``
is unchanged.
"""

from __future__ import annotations

import re

from app.services.imports.distributor_sales_inventory import _product_token_key

# ASUS-style model codes: letter(s) + digits + letters + hyphen + alphanumeric suffix.
# Examples: B1502CVA-I58512B9X, FA506NF-58512B0W, UX3402ZA-OI58512BL0W
_SALES_MODEL_CODE_RE = re.compile(
    r"\b([a-z]{1,3}\d{3,5}[a-z]{2,6}-[a-z0-9]{4,24})\b",
    re.IGNORECASE,
)

_GENERIC_DERIVED_BLOCKLIST = frozenset(
    {
        "to-be-mapped",
        "tbd",
        "unknown",
        "n/a",
        "na",
        "nan",
        "none",
        "null",
    }
)

# Final hyphen segments distributors append for dealer/channel/demo tagging.
# Allowlist only — do not peel arbitrary trailing segments (OEM codes can end in letters).
# -CM = Computer Mania, -E = Evetech (and similar), -DEMO/-DEM = demo units of the base model.
_CHANNEL_SUFFIX_SEGMENTS = frozenset({"cm", "e", "demo", "dem"})


def channel_suffix_stripped_key(full_token_key: str) -> str | None:
    """If *full_token_key* ends with a known dealer/channel suffix, return the base key."""
    key = (full_token_key or "").strip().lower()
    if not key or "-" not in key:
        return None
    left, _, right = key.rpartition("-")
    if right in _CHANNEL_SUFFIX_SEGMENTS and left:
        return left
    return None


def trailing_separator_bases(key: str) -> tuple[str, ...]:
    """One-level base after the final ``-`` or ``_`` trailer (tenant-agnostic).

    Evidence-gated callers try the full key first; these bases are only meaningful when
    the full key misses PM exact lookup. No recursion, no ASUS trailer vocabulary —
    catalogue presence of the base is what gates acceptance.
    """
    k = (key or "").strip().lower()
    if not k:
        return ()
    cut = max(k.rfind("-"), k.rfind("_"))
    if cut <= 0:
        return ()
    base = k[:cut]
    trailer = k[cut + 1 :]
    if not base or not trailer:
        return ()
    return (base,)


def _is_valid_derived_sales_model_code(candidate: str) -> bool:
    c = candidate.strip().lower()
    if not c or c in _GENERIC_DERIVED_BLOCKLIST:
        return False
    if len(c) < 10 or len(c) > 40:
        return False
    if "-" not in c:
        return False
    left, _, right = c.partition("-")
    if len(left) < 6 or len(right) < 4:
        return False
    if not re.fullmatch(r"[a-z0-9]+", left) or not re.fullmatch(r"[a-z0-9]+", right):
        return False
    if not re.search(r"\d", left):
        return False
    return True


def extract_derived_sales_model_codes(raw: str | None) -> tuple[str, ...]:
    """Return strict derived sales-model codes from *raw* (lowercase, unique, ordered)."""
    if raw is None:
        return ()
    text = str(raw).strip()
    if not text:
        return ()
    seen: set[str] = set()
    out: list[str] = []
    for m in _SALES_MODEL_CODE_RE.finditer(text):
        tk = _product_token_key(m.group(1))
        if not tk or not _is_valid_derived_sales_model_code(tk):
            continue
        if tk in seen:
            continue
        seen.add(tk)
        out.append(tk)
    return tuple(out)


def product_identity_lookup_keys(raw: str | None) -> tuple[str, ...]:
    """Ordered unique keys for PM / shipment identity matching.

    Order: full ``_product_token_key`` → legacy channel-suffix strip (``-CM``/``-E``/``-DEMO``)
    → one-level ``-``/``_`` trailer base → derived embedded sales-model codes.

    Trailer bases are only meaningful when the full key misses exact PM lookup — callers that
    short-circuit on the first hit keep OEM hyphenated full codes from false peel (e.g.
    ``FA506NF-58512B0W`` hits before ``FA506NF`` is consulted). Candidate ``normalized_key``
    stays the full token.
    """
    full = _product_token_key(raw)
    derived = extract_derived_sales_model_codes(raw)
    if not full:
        return derived
    seen: set[str] = {full}
    ordered: list[str] = [full]
    stripped = channel_suffix_stripped_key(full)
    if stripped and stripped not in seen:
        seen.add(stripped)
        ordered.append(stripped)
    for base in trailing_separator_bases(full):
        if base not in seen:
            seen.add(base)
            ordered.append(base)
    for dk in derived:
        if dk not in seen:
            seen.add(dk)
            ordered.append(dk)
    return tuple(ordered)
