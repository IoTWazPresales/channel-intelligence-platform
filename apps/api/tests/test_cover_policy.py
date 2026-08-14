"""Unit 15A — per-customer cover policy (mocked; no cip writes)."""

from __future__ import annotations

from types import SimpleNamespace

from app.services.lineup.cover_policy import (
    COVER_SOURCE_CUSTOMER_TERM,
    COVER_SOURCE_MIXED,
    COVER_SOURCE_OVERRIDE,
    COVER_SOURCE_TENANT_DEFAULT,
    TENANT_DEFAULT_COVER_WEEKS,
    share_weighted_cover_weeks,
    weeks_from_term,
)


def test_weeks_from_term_uses_customer_then_default():
    assert weeks_from_term(None) == (TENANT_DEFAULT_COVER_WEEKS, COVER_SOURCE_TENANT_DEFAULT)
    assert weeks_from_term(SimpleNamespace(target_cover_weeks=None)) == (
        TENANT_DEFAULT_COVER_WEEKS,
        COVER_SOURCE_TENANT_DEFAULT,
    )
    assert weeks_from_term(SimpleNamespace(target_cover_weeks=8)) == (8.0, COVER_SOURCE_CUSTOMER_TERM)


def test_share_weighted_mixed_and_single_source():
    weeks = {1: (8.0, COVER_SOURCE_CUSTOMER_TERM), 2: (4.0, COVER_SOURCE_TENANT_DEFAULT)}
    mixed_shares = [
        {"customer_id": 1, "share": 0.5},
        {"customer_id": 2, "share": 0.5},
    ]
    w, src = share_weighted_cover_weeks(
        mixed_shares,
        weeks,
        fallback_weeks=TENANT_DEFAULT_COVER_WEEKS,
        fallback_source=COVER_SOURCE_TENANT_DEFAULT,
    )
    assert w == 6.0
    assert src == COVER_SOURCE_MIXED

    one = share_weighted_cover_weeks(
        [{"customer_id": 1, "share": 1.0}],
        weeks,
        fallback_weeks=TENANT_DEFAULT_COVER_WEEKS,
        fallback_source=COVER_SOURCE_TENANT_DEFAULT,
    )
    assert one == (8.0, COVER_SOURCE_CUSTOMER_TERM)


def test_empty_shares_uses_fallback_and_override_source():
    w, src = share_weighted_cover_weeks(
        [],
        {},
        fallback_weeks=10.0,
        fallback_source=COVER_SOURCE_OVERRIDE,
    )
    assert w == 10.0
    assert src == COVER_SOURCE_OVERRIDE


def test_customer_term_changes_cover_units_vs_default():
    """Same velocity: 8w customer term vs 4w default → cover units double."""
    weekly = 2.0
    customer_weeks, _ = weeks_from_term(SimpleNamespace(target_cover_weeks=8))
    default_weeks, _ = weeks_from_term(None)
    assert customer_weeks * weekly == 16.0
    assert default_weeks * weekly == TENANT_DEFAULT_COVER_WEEKS * weekly
    assert customer_weeks * weekly != default_weeks * weekly
