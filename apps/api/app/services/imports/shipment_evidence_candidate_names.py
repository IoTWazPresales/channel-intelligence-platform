"""Display-name hints for shipment evidence mapping candidates (rebuild-time ``context.suggested_name``)."""

from __future__ import annotations

import re

# Corporate / legal suffix tokens stripped before title-casing distributor labels.
_RE_DIST_SUFFIX = re.compile(
    r"\s*,?\s*(inc\.?|llc\.?|ltd\.?|limited|plc\.?|corp\.?|corporation|co\.?|company|pty\.?|"
    r"gmbh|s\.a\.|s\.p\.a\.|nv|bv|ag)\s*$",
    re.IGNORECASE,
)


# Strip ISO-style region segment and trailing branch codes (e.g. MUSTEK-ZA-BB → Mustek).
_RE_DIST_REGION_TAIL = re.compile(r"(?i)-[a-z]{2}-.*$")


def suggested_name_for_distributor_token(raw: str) -> str:
    """Strip common distributor suffix patterns, region/branch tail (-XX-…), collapse spaces, title case."""
    s = (raw or "").strip()
    if not s:
        return ""
    s = _RE_DIST_REGION_TAIL.sub("", s).strip()
    s = _RE_DIST_SUFFIX.sub("", s).strip()
    s = re.sub(r"\s+", " ", s)
    return _soft_title(s)[:256]


def suggested_name_for_customer_token(raw: str) -> str:
    """Display hint when no per-job statistics are available (delegates to shared naming pipeline)."""
    from app.services.imports.shipment_evidence_customer_token_naming import (
        detect_statistical_prefixes,
        suggest_customer_token_name,
    )

    s = (raw or "").strip()
    if not s:
        return ""
    prefs, _ = detect_statistical_prefixes([s])
    out = suggest_customer_token_name(s, statistical_prefixes_longest_first=prefs, source_def=None)
    return (out.suggested_name or _soft_title(s)[:256])[:256]


def _soft_title(s: str) -> str:
    """Title case words while keeping short all-caps tokens (<=4) uppercase."""
    parts: list[str] = []
    for w in s.split(" "):
        if not w:
            continue
        core = w.strip(".,()[]")
        if len(core) <= 4 and core.isalpha() and core.isupper():
            parts.append(w)
        else:
            parts.append(w[:1].upper() + w[1:].lower() if len(w) > 1 else w.upper())
    return " ".join(parts)
