"""Open Channel effective customer grain for lineup planned qty."""
from types import SimpleNamespace

from app.services.commercial_planner.lineup_open_channel import effective_lineup_customer_id


def test_effective_lineup_customer_id_mapped_customer():
    ln = SimpleNamespace(customer_id=7, raw_row_payload={})
    assert effective_lineup_customer_id(ln, open_channel_customer_id=99) == 7


def test_effective_lineup_customer_id_open_channel_staging():
    ln = SimpleNamespace(
        customer_id=None,
        raw_row_payload={"staging_open_channel": True},
    )
    assert effective_lineup_customer_id(ln, open_channel_customer_id=42) == 42


def test_effective_lineup_customer_id_unresolved_not_open_channel():
    ln = SimpleNamespace(customer_id=None, raw_row_payload={})
    assert effective_lineup_customer_id(ln, open_channel_customer_id=42) is None
