"""Names beside ids on query results (Warren 2026-10-20)."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.query.labels import attach_names


def _result(rows):
    res = MagicMock()
    res.all.return_value = rows
    return res


@pytest.mark.anyio
async def test_names_added_beside_ids():
    db = AsyncMock()
    db.execute.side_effect = [
        _result([SimpleNamespace(id=11, name="Amazon SA")]),
        _result([SimpleNamespace(id=2, name="Disti One")]),
        _result([SimpleNamespace(id=21, sales_model_name="X1407VA", name="Vivobook 14", sku="90NB0007")]),
    ]
    rows = [{"customer_id": 11, "product_id": 21, "value": 5}, {"distributor_id": 2, "value": 1}]
    await attach_names(db, rows)
    assert rows[0]["customer_name"] == "Amazon SA" and rows[0]["product_name"] == "X1407VA"
    assert rows[1]["distributor_name"] == "Disti One"
    assert rows[0]["customer_id"] == 11  # ids stay for filtering


@pytest.mark.anyio
async def test_lookup_failure_leaves_rows_alone():
    db = AsyncMock()
    db.execute.side_effect = RuntimeError("db down")
    rows = [{"customer_id": 11, "value": 5}]
    await attach_names(db, rows)
    assert rows == [{"customer_id": 11, "value": 5}]
