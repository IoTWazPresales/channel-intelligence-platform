"""BACKLOG-061 B3 — distributor promote unit tests (no cip writes)."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from app.services.distributor_promote import (
    BULK_UPSERT_TMP_DUPLICATE_WARNING,
    PROMOTE_TARGET_STATUS,
    DistributorPromoteError,
    _eligibility,
    confirm_distributor_promote,
    preview_distributor_promote,
)


def _row(**kwargs):
    base = dict(
        id=10,
        code="TMP-DIST-ABC",
        name="Disti",
        distributor_status="active",
        merged_into_distributor_id=None,
        merge_note=None,
    )
    base.update(kwargs)
    return SimpleNamespace(**base)


def _db_with(row, owner=None):
    db = AsyncMock()
    db.get = AsyncMock(return_value=row)

    async def _exec(_stmt):
        result = MagicMock()
        result.scalars.return_value.first.return_value = owner
        return result

    db.execute = AsyncMock(side_effect=_exec)
    db.commit = AsyncMock()
    db.refresh = AsyncMock()
    db.add = MagicMock()
    return db


def test_eligibility_tmp_active():
    e = _eligibility(_row())
    assert e["eligible"] is True
    assert e["admin_mint_edge"] is True


def test_eligibility_rejects_non_tmp():
    e = _eligibility(_row(code="DIST-1"))
    assert e["eligible"] is False


def test_preview_and_confirm():
    row = _row()
    out = asyncio.run(preview_distributor_promote(_db_with(row), distributor_id=10, new_code="DIST-REAL"))
    assert out["can_confirm"] is True
    assert BULK_UPSERT_TMP_DUPLICATE_WARNING in out["warnings"]

    db = _db_with(row)
    conf = asyncio.run(confirm_distributor_promote(db, distributor_id=10, new_code="DIST-REAL", note="ok"))
    assert conf["applied"] is True
    assert row.code == "DIST-REAL"
    assert row.distributor_status == PROMOTE_TARGET_STATUS
    assert row.merged_into_distributor_id is None


def test_confirm_collision():
    row = _row()
    other = _row(id=20, code="DIST-REAL")
    try:
        asyncio.run(confirm_distributor_promote(_db_with(row, other), distributor_id=10, new_code="DIST-REAL"))
        raise AssertionError("expected error")
    except DistributorPromoteError as e:
        assert e.status_code == 409
