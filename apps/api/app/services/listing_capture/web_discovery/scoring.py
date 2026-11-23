"""Decide what to do with a candidate site. Pure: no database, no network, no clock.

A site is saved automatically only on exact evidence from three independent signals:

- ``name_exact``: the domain's name part equals one of the customer's name keys (exact string
  equality, never a fuzzy score),
- ``country_match``: the tenant's country, from the domain ending or the home page,
- ``found_by_product_search``: a web search for one of the customer's products returned the site.

Anything less that loaded goes to a steward queue with the evidence. The ranking of the queue is a
display order, not a score.
"""

from __future__ import annotations

import re
from typing import Any

from app.services.imports.dsi_customer_name_normalization import customer_similarity_lookup_keys
from app.services.listing_capture.web_discovery.homepage import HomeSignals

OUTCOME_AUTO = "auto_accept"
OUTCOME_USER = "user_confirmed"
OUTCOME_QUEUE = "steward_queue"
OUTCOME_MONITORED = "already_monitored"
OUTCOME_REJECTED = "already_rejected"
OUTCOME_DROPPED = "dropped"

SOURCE_ON_FILE = "on_file"
SOURCE_EMAIL = "email"
SOURCE_PRODUCT_SEARCH = "product_search"
SOURCE_NAME_SEARCH = "name_search"
SOURCE_GUESS = "guess"
SOURCE_USER = "user"

MAX_QUEUED_PER_CUSTOMER = 5

HOW_CCTLD = "cctld"
HOW_ADDRESS = "address_country"
HOW_LOCALE = "page_locale"

# "Acme | Shop", "Acme - Shop", "Shop: Acme", "Acme · Shop". A hyphen or dash splits only when
# spaces surround it, so "e-shop" stays one word.
_TITLE_SPLIT = re.compile(r"\s*[|:·]\s*|\s+[–—-]\s+")
_NON_ALNUM = re.compile(r"[^a-z0-9]")


def normalize_host(host: str) -> str:
    return (host or "").strip().lower().rstrip(".").removeprefix("www.")


def customer_keys(name: str | None) -> list[str]:
    """The customer's name keys: the existing normaliser's keys, reduced to ``a-z0-9``. No empties."""
    out: list[str] = []
    for key in customer_similarity_lookup_keys(name):
        reduced = _NON_ALNUM.sub("", key.lower())
        if reduced and reduced not in out:
            out.append(reduced)
    return out


def matched_ending(host: str, endings: list[str]) -> str | None:
    """The longest configured ending the host ends with (with a name part before it)."""
    host = normalize_host(host)
    for ending in sorted(endings, key=len, reverse=True):
        if host.endswith(ending) and len(host) > len(ending):
            return ending
    return None


def domain_key(host: str, endings: list[str]) -> str:
    """The host's name part: strip ``www.``, strip the longest configured ending (else the last
    label), take the last remaining label, remove hyphens."""
    host = normalize_host(host)
    ending = matched_ending(host, endings)
    if ending is not None:
        stripped = host[: -len(ending)]
    else:
        labels = host.split(".")
        stripped = ".".join(labels[:-1]) if len(labels) > 1 else host
    label = stripped.split(".")[-1] if stripped else ""
    return label.replace("-", "")


def name_match(host: str, name: str | None, endings: list[str]) -> dict[str, Any]:
    keys = customer_keys(name)
    dk = domain_key(host, endings)
    return {"exact": bool(dk) and dk in keys, "customer_keys": keys, "domain_key": dk}


def country_match(
    host: str,
    endings: list[str],
    country: dict[str, str] | None,
    home: HomeSignals | None,
) -> dict[str, Any]:
    """``{"value": bool, "how": "cctld"|"address_country"|"page_locale"|None}``."""
    if not country:
        return {"value": False, "how": None}
    code = country["code"].lower()
    ending = matched_ending(host, endings)
    if ending is not None:
        last = ending.rsplit(".", 1)[-1]
        if len(last) == 2 and last == code:
            return {"value": True, "how": HOW_CCTLD}
    if home is not None:
        wanted = {country["code"].casefold(), country["name"].casefold()}
        if any(value.casefold() in wanted for value in home.address_countries):
            return {"value": True, "how": HOW_ADDRESS}
        for tag in (home.html_lang, home.og_locale):
            parts = re.split(r"[-_]", tag or "")
            if any(len(part) == 2 and part.lower() == code for part in parts[1:]):
                return {"value": True, "how": HOW_LOCALE}
    return {"value": False, "how": None}


def _segment_keys(text: str | None) -> set[str]:
    return set(customer_keys(text)) if text else set()


def homepage_match(home: HomeSignals | None, keys: list[str]) -> dict[str, Any]:
    """The home page names the customer: ``og:site_name``, a JSON-LD organisation name, or a title
    segment whose normalised key equals one of the customer's keys."""
    if home is None or not keys:
        return {"match": False, "via": None}
    wanted = set(keys)
    if _segment_keys(home.og_site_name) & wanted:
        return {"match": True, "via": "og_site_name"}
    for org in home.org_names:
        if _segment_keys(org) & wanted:
            return {"match": True, "via": "org_name"}
    for segment in _TITLE_SPLIT.split(home.title or ""):
        if _segment_keys(segment) & wanted:
            return {"match": True, "via": "title"}
    return {"match": False, "via": None}


def build_evidence(
    *,
    host: str,
    customer_name: str | None,
    sources: set[str],
    endings: list[str],
    country: dict[str, str] | None,
    home: HomeSignals | None,
    http_status: int | None,
    final_url: str | None,
    robots: str,
    product_hits: list[dict[str, Any]],
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """The evidence shown in a Preview and stored with a saved site. No email address, ever."""
    names = name_match(host, customer_name, endings)
    matched = homepage_match(home, names["customer_keys"])
    evidence: dict[str, Any] = {
        "sources": sorted(sources),
        "name_match": names,
        "ending_match": matched_ending(host, endings),
        "country_match": country_match(host, endings, country, home),
        "homepage": {
            "http_status": http_status,
            "final_url": final_url,
            "title": home.title if home else None,
            "org_name": (home.org_names[0] if home and home.org_names else None)
            or (home.og_site_name if home else None),
            "match": matched["match"],
            "via": matched["via"],
        },
        "product_search_hits": list(product_hits),
        "robots": robots,
    }
    if home is not None:
        # Kept so Apply can re-derive the decision from what the page said.
        evidence["home_signals"] = home.to_dict()
    if extra:
        evidence.update(extra)
    return evidence


def _bool(value: Any) -> bool:
    return value is True


def decide(
    evidence: dict[str, Any],
    *,
    user_entered: bool = False,
    rejected: bool = False,
    already_monitored: bool = False,
) -> str:
    """The outcome for a candidate that loaded. Preview and Apply both call this, so a stored plan
    cannot raise an item to ``auto_accept`` by editing its outcome."""
    if rejected:
        return OUTCOME_REJECTED
    if already_monitored:
        return OUTCOME_MONITORED
    if user_entered:
        return OUTCOME_USER
    names = evidence.get("name_match") or {}
    keys = [str(k) for k in names.get("customer_keys") or []]
    key = str(names.get("domain_key") or "")
    exact = bool(key) and key in keys
    country = _bool((evidence.get("country_match") or {}).get("value"))
    searched = bool(evidence.get("product_search_hits"))
    home_ok = int((evidence.get("homepage") or {}).get("http_status") or 0) == 200
    robots_ok = evidence.get("robots") == "allowed"
    if exact and country and searched and home_ok and robots_ok:
        return OUTCOME_AUTO
    return OUTCOME_QUEUE


def rank_key(evidence: dict[str, Any]) -> tuple[int, int, int, int, int, int]:
    """Sort key (ascending = best first): name, country, product hits, home page, on file, email.

    A display order for the review queue, not a score."""
    sources = set(evidence.get("sources") or [])
    names = evidence.get("name_match") or {}
    return (
        0 if names.get("exact") else 1,
        0 if (evidence.get("country_match") or {}).get("value") else 1,
        -len(evidence.get("product_search_hits") or []),
        0 if (evidence.get("homepage") or {}).get("match") else 1,
        0 if SOURCE_ON_FILE in sources else 1,
        0 if SOURCE_EMAIL in sources else 1,
    )
