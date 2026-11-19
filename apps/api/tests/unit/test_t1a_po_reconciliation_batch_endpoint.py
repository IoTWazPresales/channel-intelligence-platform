"""T1a: GET /lineup/po-reconciliation/batch - one request for many cases."""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

import pytest
from app.api.v1.endpoints import commercial_planner as ep
from fastapi import HTTPException


def _call(case_ids: str, payloads: dict[int, dict] | None = None):
    batch = AsyncMock(return_value=payloads if payloads is not None else {})
    with patch.object(ep, "reconcile_cases", batch):
        out = asyncio.run(ep.get_po_reconciliation_batch(case_ids=case_ids, db=AsyncMock()))
    return out, batch


def test_batch_returns_payload_per_case_and_lists_unknown_ids():
    payloads = {1: {"case_id": 1, "summary": {}}, 2: {"case_id": 2, "summary": {}}}
    out, batch = _call("1,2,3", payloads)
    assert batch.await_count == 1
    assert batch.await_args.args[1] == [1, 2, 3]
    assert out["items"] == {"1": payloads[1], "2": payloads[2]}
    assert out["missing_case_ids"] == [3]


def test_batch_dedupes_and_tolerates_whitespace():
    out, batch = _call(" 2, 1 ,2,,1 ", {1: {"case_id": 1}, 2: {"case_id": 2}})
    assert batch.await_args.args[1] == [2, 1]
    assert out["missing_case_ids"] == []


@pytest.mark.parametrize("raw", ["", " , ", "a,b", "1,x", "0", "-4"])
def test_batch_rejects_bad_lists(raw):
    with pytest.raises(HTTPException) as exc:
        _call(raw)
    assert exc.value.status_code == 422


def test_batch_caps_the_list():
    ok, _ = _call(",".join(str(i) for i in range(1, ep.PO_RECONCILIATION_BATCH_MAX + 1)))
    assert ok["missing_case_ids"] != []  # accepted at the cap
    with pytest.raises(HTTPException) as exc:
        _call(",".join(str(i) for i in range(1, ep.PO_RECONCILIATION_BATCH_MAX + 2)))
    assert exc.value.status_code == 422
