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
    # Takealot WEEK "Product ID" is a SKU, never a PLID. A URL is suggested only for an
    # explicit ``PLID<n>`` token. Product-page shape needs a path segment before the
    # PLID: bare ``/PLID<n>`` routes to Takealot's seo-landing page, not the product.
    "takealot": "https://www.takealot.com/x/PLID{external_id}",
    # Evetech Web IDs resolve via a category mid-path; site rewrites to canonical slug.
    # Verified for ASUS laptop Web IDs (trailing numeric id). Steward may still edit.
    "evetech": "https://www.evetech.co.za/asus-laptops/laptops-for-sale/{external_id}",
}

_ASIN_RE = re.compile(r"^B0[A-Z0-9]{8}$", re.IGNORECASE)
_PLID_RE = re.compile(r"^PLID\s*(\d{5,12})$", re.IGNORECASE)
_EVETECH_WEB_ID_RE = re.compile(r"^\d{4,8}$")


def takealot_product_url(plid: str | int, *, canonical_url: str | None = None) -> str:
    """Takealot product-page URL for a known real PLID.

    Uses the canonical slug URL when it is a takealot.com URL ending in this PLID,
    else ``https://www.takealot.com/x/PLID<n>``. Never pass a report SKU here.
    """
    digits = re.sub(r"\D", "", str(plid))
    if not digits:
        raise ValueError("PLID required")
    canon = (canonical_url or "").strip()
    if (
        canon.startswith("https://www.takealot.com/")
        and re.search(rf"/PLID{digits}(?:[/?#]|$)", canon, re.IGNORECASE)
        and not re.match(r"^https://www\.takealot\.com/PLID\d+", canon, re.IGNORECASE)
    ):
        return canon
    return f"https://www.takealot.com/x/PLID{digits}"


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
        # Only an explicit PLID token is a PLID. Bare digits are the report SKU:
        # no URL (the steward pastes one, or poll-time EAN resolution finds the PLID).
        m = _PLID_RE.match(ext.replace(" ", ""))
        if not m:
            return None
        return takealot_product_url(m.group(1))

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
