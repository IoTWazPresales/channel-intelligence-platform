"""Tests for OPEN_CHANNEL absorb (dedicated path — not general merge survivor)."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from app.services import open_channel_absorb as oc


def test_preview_rejects_empty_note() -> None:
    with pytest.raises(oc.OpenChannelAbsorbError, match="audit_note"):
        oc.preview_absorb_into_open_channel(MagicMock(), loser_ids=[19], audit_note="  ")


def test_preview_rejects_survivor_in_losers(monkeypatch) -> None:
    db = MagicMock()
    monkeypatch.setattr(oc, "resolve_open_channel_id", lambda _db: 1)
    with pytest.raises(oc.OpenChannelAbsorbError, match="cannot be listed as a loser"):
        oc.preview_absorb_into_open_channel(db, loser_ids=[1, 19], audit_note="note")


def test_preview_happy_path(monkeypatch) -> None:
    db = MagicMock()
    monkeypatch.setattr(oc, "resolve_open_channel_id", lambda _db: 1)
    survivor = MagicMock(code="OPEN_CHANNEL", id=1)
    loser = MagicMock(code="TMP-OC", name="Open Channel", customer_status="active", merged_into_customer_id=None)

    def _get(_cls, cid):
        if cid == 1:
            return survivor
        if cid == 19:
            return loser
        return None

    db.get.side_effect = _get
    monkeypatch.setattr(oc, "count_customer_fk_refs", lambda _db, _cid: {"fact_sales_sellout.customer_id": 3})
    out = oc.preview_absorb_into_open_channel(
        db, loser_ids=[19], audit_note="repair", expected_survivor_id=1
    )
    assert out["survivor_id"] == 1
    assert out["loser_ids"] == [19]
    assert out["loser_plans"][0]["fk_breakdown"][0]["count"] == 3
