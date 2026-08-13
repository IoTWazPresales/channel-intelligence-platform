"""Listing URL auto-finder — report IDs → retailer URL candidates for human check.

Never auto-registers listings. Steward confirms (or edits) the suggested URL.
"""

from __future__ import annotations

import re
from typing import Any

# Marketplace → URL template. `{external_id}` is the feed/report ID (ASIN, PLID, …).
# Keep templates generic; steward may edit before confirm.
_LISTING_URL_TEMPLATES: dict[str, str] = {
    "amazon": "https://www.amazon.co.za/dp/{external_id}",
    # Takealot WEEK "Product ID" is a SKU; poll resolves PLID via REST + EAN.
    # Template still prefixes PLID so a real PLID paste keeps working; SKU URLs 404
    # and are recovered at fetch time (not here — no live HTTP in suggest).
    "takealot": "https://www.takealot.com/PLID{external_id}",
    # Evetech Web IDs resolve via a category mid-path; site rewrites to canonical slug.
    # Verified for ASUS laptop Web IDs (trailing numeric id). Steward may still edit.
    "evetech": "https://www.evetech.co.za/asus-laptops/laptops-for-sale/{external_id}",
}

_ASIN_RE = re.compile(r"^B0[A-Z0-9]{8}$", re.IGNORECASE)
_PLID_RE = re.compile(r"^(?:PLID)?(\d{5,12})$", re.IGNORECASE)
_EVETECH_WEB_ID_RE = re.compile(r"^\d{4,8}$")


def suggest_listing_url(marketplace: str, external_id: str) -> str | None:
    """Build a candidate PDP URL from marketplace + feed external_id, or None."""
    mkt = (marketplace or "").strip().lower()
    ext = (external_id or "").strip()
    if not mkt or not ext:
        return None
    template = _LISTING_URL_TEMPLATES.get(mkt)
    if not template:
        return None

    if mkt == "amazon":
        # Accept bare ASIN only — refuse garbage tokens.
        if not _ASIN_RE.match(ext):
            return None
        return template.format(external_id=ext.upper())

    if mkt == "takealot":
        # Accept bare digits or PLID-prefixed; strip spaces (sales sheet "222 547 542").
        digits = re.sub(r"\D", "", ext)
        m = _PLID_RE.match(digits) or _PLID_RE.match(ext)
        if not m:
            # Prefer pure digit product ids 5–12 long after stripping.
            if not re.fullmatch(r"\d{5,12}", digits):
                return None
            return template.format(external_id=digits)
        return template.format(external_id=m.group(1))

    if mkt == "evetech":
        digits = re.sub(r"\D", "", ext)
        if not _EVETECH_WEB_ID_RE.match(digits):
            return None
        return template.format(external_id=digits)

    return template.format(external_id=ext)


def enrich_proposal_with_suggested_url(proposal: dict[str, Any]) -> dict[str, Any]:
    """Attach ``suggested_url`` for steward confirm prefill (human check still required)."""
    out = dict(proposal)
    out["suggested_url"] = suggest_listing_url(
        str(proposal.get("marketplace") or ""),
        str(proposal.get("external_id") or ""),
    )
    return out
