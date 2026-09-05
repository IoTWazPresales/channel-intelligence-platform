"""Unit tests for payment-evidence overlay helpers (no DB)."""

from __future__ import annotations

from app.services.cpor.payment_evidence.overlay_read import (
    latest_comment_from_raw,
    raw_lookup,
)


def test_raw_lookup_matches_header_with_newline():
    raw = {"Latest Comment\n": "overclaim 75 units, please check and update."}
    assert latest_comment_from_raw(raw) == "overclaim 75 units, please check and update."


def test_raw_lookup_skips_blank_then_hits_alias():
    raw = {"Latest Comment": "   ", "Remark": "kept"}
    assert raw_lookup(raw, "Latest Comment") is None
    assert raw_lookup(raw, "Latest Comment", "Remark") == "kept"


def test_latest_comment_none_on_empty_raw():
    assert latest_comment_from_raw(None) is None
    assert latest_comment_from_raw({}) is None
