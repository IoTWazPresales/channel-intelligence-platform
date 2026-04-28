"""Unit tests for Open Channel staging helpers and sync eligibility (no DB migrations)."""

from types import SimpleNamespace

from app.api.v1.endpoints.commercial_planner import SyncToPlanRequest, _sync_eligibility
from app.services.commercial_planner.lineup_open_channel import (
    extract_distributor_name_from_channel_customer_cell,
    managed_customer_token_unresolved,
    sync_skip_detail_message,
)


def test_channel_cell_extracts_distributor_hint():
    assert extract_distributor_name_from_channel_customer_cell("Channel - Rectron/Mustek") == "Rectron/Mustek"
    assert extract_distributor_name_from_channel_customer_cell("  channel-  Pinnacle ") == "Pinnacle"
    assert extract_distributor_name_from_channel_customer_cell("Retail Co") is None


def test_managed_customer_token_unresolved_ignores_open_channel_staging():
    ln = SimpleNamespace(
        customer_token="ACME",
        customer_id=None,
        raw_row_payload={"staging_open_channel": True},
    )
    assert managed_customer_token_unresolved(ln) is False


def test_sync_eligibility_open_channel_requires_customer_or_fallback():
    body = SyncToPlanRequest()
    ln = SimpleNamespace(
        product_id=1,
        customer_id=None,
        distributor_id=1,
        msrp_local=10.0,
        quantity_units=1.0,
        customer_token=None,
        raw_row_payload={"staging_open_channel": True},
    )
    eligible, reason, *_ = _sync_eligibility(ln, body, set())
    assert eligible is False
    assert reason == "planner_requires_customer"
    detail = sync_skip_detail_message(ln, reason)
    assert detail and "Open Channel" in detail

    body2 = SyncToPlanRequest(fallback_customer_id=99)
    eligible2, reason2, *_ = _sync_eligibility(ln, body2, set())
    assert eligible2 is True
    assert reason2 == ""


def test_sync_eligibility_managed_unresolved_customer_blocks():
    body = SyncToPlanRequest()
    ln = SimpleNamespace(
        product_id=1,
        customer_id=None,
        distributor_id=1,
        msrp_local=10.0,
        quantity_units=1.0,
        customer_token="UNKNOWN",
        raw_row_payload={},
    )
    eligible, reason, *_ = _sync_eligibility(ln, body, set())
    assert eligible is False
    assert reason == "missing_customer"
