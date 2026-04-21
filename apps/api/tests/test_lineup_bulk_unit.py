from pydantic import ValidationError

from app.api.v1.endpoints.lineup import LineupBulkBody, LineupBulkRow
from app.services.lineup.bulk import dedupe_lineup_input_rows


def test_dedupe_lineup_input_rows_last_wins():
    rows = [
        {"customer_code": "A", "channel_code": "", "period_start": "2026-01-01", "sku": "S1"},
        {"customer_code": "A", "channel_code": "", "period_start": "2026-01-01", "sku": "S1", "notes": "second"},
    ]
    out = dedupe_lineup_input_rows(rows)
    assert len(out) == 1
    idx, r = out[0]
    assert idx == 1
    assert r["notes"] == "second"


def test_lineup_bulk_body_rejects_too_many_rows():
    rows = [LineupBulkRow(customer_code="C", period_start="2026-01-01", sku="S")] * 2001
    try:
        LineupBulkBody(rows=rows, replace_matching=False)
    except ValidationError as e:
        assert "2000" in str(e)
    else:
        raise AssertionError("expected ValidationError")
