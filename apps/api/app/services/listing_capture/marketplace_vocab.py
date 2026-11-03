"""Listing Capture v0 — listing vocabulary (spec §8).

Sites are tenant data (``listing_site``), not a list here. Not DB enums — stored as varchar.
"""

from __future__ import annotations

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

PARSER_VERSION = "lc-v0.3"
