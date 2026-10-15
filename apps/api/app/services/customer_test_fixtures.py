"""Recognise test-fixture ``dim_customer`` rows left on shared databases by test runs.

Used to keep fixtures out of steward worklists counts and out of repair/backfill scripts.
Nothing here deletes or edits a fixture: Warren removes test data separately.

Real customers carry a system code: ``TMP-CUST-…`` (provisional), ``CUST-…`` (promoted) or
``OPEN_CHANNEL``. Test runs mint other shapes (``C-FULL-…``, ``C-REL-…``, ``KEEP-…``, ``DG-…``,
``TECHGRP-1`` …) and a few fixture names that also appear with real-looking codes.
"""

from __future__ import annotations

import re

from app.services.commercial_planner.open_channel_customer import OPEN_CHANNEL_CUSTOMER_CODE

_REAL_CODE_RE = re.compile(r"^(TMP-CUST-|CUST-)", re.IGNORECASE)
_FIXTURE_NAME_RE = re.compile(
    r"^(RelAmazon\b|Acme Retail [0-9a-f]{8}\b|Abort Merge|Merge Test|Term Dedup|Bulk Preview|Alias Customer )",
    re.IGNORECASE,
)


def is_test_fixture_customer(code: str | None, name: str | None) -> bool:
    """True when the row looks like a test fixture rather than a real customer."""
    c = (code or "").strip()
    if c.upper() == OPEN_CHANNEL_CUSTOMER_CODE:
        return False
    if not _REAL_CODE_RE.match(c):
        return True
    return bool(_FIXTURE_NAME_RE.match((name or "").strip()))
