"""Listing Capture v0 — marketplace config vocabulary (spec §8).

Steward-extendable later; not a DB enum — stored as varchar.
"""

from __future__ import annotations

LISTING_MARKETPLACES: tuple[str, ...] = ("takealot", "evetech")
LISTING_MARKETPLACE_SET: frozenset[str] = frozenset(LISTING_MARKETPLACES)

LISTING_STATUSES: tuple[str, ...] = (
    "active",
    "out_of_stock",
    "delisted",
    "dead_link",
)
LISTING_STATUS_SET: frozenset[str] = frozenset(LISTING_STATUSES)

LISTING_SOURCES: tuple[str, ...] = ("manual", "csv_import", "feed_proposal")
LISTING_SOURCE_SET: frozenset[str] = frozenset(LISTING_SOURCES)

LISTING_PARSE_STATUSES: tuple[str, ...] = ("ok", "parse_failed", "skipped")
LISTING_PARSE_STATUS_SET: frozenset[str] = frozenset(LISTING_PARSE_STATUSES)

PARSER_VERSION = "lc-v0.1"
