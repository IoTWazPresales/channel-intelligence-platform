"""Unit 6b — customer-token stamp helpers (no DB)."""

from __future__ import annotations

from app.services.commercial_planner.lineup_customer_token_stamp import (
    CONFLICT_DISPOSITIONS,
    CustomerTokenConflictError,
    CustomerTokenStampError,
)
from app.services.imports.distributor_sales_inventory import _norm_key
from app.services.imports.shipment_evidence_resolution_plan import (
    build_unique_approved_customer_alias_id_by_token,
)


def test_norm_key_stable_for_stamp_tokens():
    assert _norm_key("SADC - Compuspeed") == _norm_key("sadc - compuspeed")
    assert _norm_key("") == ""
    assert _norm_key(None) == ""


def test_unique_collapse_conflict_detector():
    rows = [
        ("sadc - dcc", 47, None),
        ("sadc - dcc", 299, None),
        ("jd furn", 1, None),
    ]
    m = build_unique_approved_customer_alias_id_by_token(rows)
    assert "sadc - dcc" not in m
    assert m["jd furn"] == 1


def test_conflict_error_carries_dispositions():
    err = CustomerTokenConflictError("sadc - dcc", [47, 299])
    assert err.competing_customer_ids == [47, 299]
    assert tuple(err.dispositions) == CONFLICT_DISPOSITIONS


def test_empty_token_norm_blocks_stamp():
    assert _norm_key("  ") == ""
    err = CustomerTokenStampError("empty token — cannot stamp; see backlog tokenless path")
    assert "empty token" in str(err)


def test_backlog_tokenless_entry_present():
    from pathlib import Path

    text = Path(__file__).resolve().parents[3].joinpath("docs", "BACKLOG.md").read_text(encoding="utf-8")
    assert "BACKLOG-124" in text
    assert "tokenless customer acquisition" in text.lower()
