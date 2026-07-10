"""BACKLOG-061-U-B3a — distributor no-code disposition (no cip writes)."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient

from app.api.deps import get_db
from app.main import app
from app.services.distributor_bulk_promote import run_distributor_bulk_promote
from app.services.distributor_disposition import run_distributor_disposition_batch
from app.services.distributor_promote import preview_distributor_promote

client = TestClient(app)


def setup_function():
    app.dependency_overrides.clear()


def teardown_function():
    app.dependency_overrides.clear()


def _row(**kwargs):
    base = dict(
        id=10,
        code="TMP-DIST-ABC",
        name="Acme Dist",
        distributor_status="active",
        merged_into_distributor_id=None,
        merge_note=None,
        no_code_disposition=None,
    )
    base.update(kwargs)
    return SimpleNamespace(**base)


def _db(rows_by_id: dict[int, SimpleNamespace]):
    db = AsyncMock()

    async def _get(_cls, pk):
        return rows_by_id.get(int(pk))

    db.get = AsyncMock(side_effect=_get)
    db.commit = AsyncMock()
    db.refresh = AsyncMock()
    db.add = MagicMock()
    return db


def test_set_parked_and_clear_round_trip():
    row = _row()
    db = _db({10: row})
    out = asyncio.run(
        run_distributor_disposition_batch(
            db, distributor_ids=[10], disposition="parked", note="junk", dry_run=False
        )
    )
    assert out["summary"]["applied"] == 1
    assert row.no_code_disposition == "parked"
    assert row.distributor_status == "active"
    assert "parked" in (row.merge_note or "")

    out2 = asyncio.run(
        run_distributor_disposition_batch(db, distributor_ids=[10], disposition="clear", dry_run=False)
    )
    assert out2["summary"]["applied"] == 1
    assert row.no_code_disposition is None
    assert row.distributor_status == "active"


def test_idempotent_re_set_skipped():
    row = _row(no_code_disposition="excluded")
    db = _db({10: row})
    out = asyncio.run(
        run_distributor_disposition_batch(
            db, distributor_ids=[10], disposition="excluded", dry_run=False
        )
    )
    assert out["summary"]["skipped"] == 1
    assert "already_set:excluded" in out["rows"][0]["reasons"]


def test_non_tmp_and_merged_blocked():
    a = _row(id=1, code="REAL-1")
    b = _row(id=2, code="TMP-DIST-X", merged_into_distributor_id=99)
    db = _db({1: a, 2: b})
    out = asyncio.run(
        run_distributor_disposition_batch(
            db, distributor_ids=[1, 2], disposition="parked", dry_run=True
        )
    )
    assert out["summary"]["blocked"] == 2
    assert "code_not_tmp_dist" in out["rows"][0]["reasons"]
    assert "row_is_merged_loser" in out["rows"][1]["reasons"]


def test_promote_blocks_disposition_row():
    row = _row(no_code_disposition="parked")
    db = _db({10: row})

    async def _exec(_stmt):
        result = MagicMock()
        result.scalars.return_value.first.return_value = None
        return result

    db.execute = AsyncMock(side_effect=_exec)
    preview = asyncio.run(preview_distributor_promote(db, distributor_id=10, new_code="ACME-1"))
    assert preview["can_confirm"] is False
    assert "disposition_parked" in preview["eligibility"]["reasons"]


def test_mint_disposition_does_not_advance_next_seq():
    row = _row(no_code_disposition="excluded")
    db = _db({10: row})

    async def _exec(stmt):
        result = MagicMock()
        key = None
        try:
            for v in stmt.compile().params.values():
                if isinstance(v, str):
                    key = v.lower()
                    break
        except Exception:
            key = None
        found = row if key and key.startswith("tmp-dist-") else None
        result.scalars.return_value.first.return_value = found
        return result

    db.execute = AsyncMock(side_effect=_exec)
    settings = SimpleNamespace(next_seq=5)

    async def _fake_mint(*_a, **_k):
        settings.next_seq += 1
        return "DIST-000005", 5

    with patch(
        "app.services.distributor_bulk_promote.mint_next_distributor_code",
        side_effect=_fake_mint,
    ):
        out = asyncio.run(
            run_distributor_bulk_promote(
                db,
                rows=[{"tmp_code": "TMP-DIST-ABC"}],
                dry_run=False,
                mode="mint",
            )
        )
    assert out["summary"]["blocked"] == 1
    assert "disposition_excluded" in out["rows"][0]["reasons"]
    assert settings.next_seq == 5


def test_list_disposition_filter_invalid():
    async def fake_db():
        yield AsyncMock()

    app.dependency_overrides[get_db] = fake_db
    r = client.get("/api/v1/distributors?disposition=bogus")
    assert r.status_code == 422
    assert r.json()["detail"]["code"] == "invalid_disposition_filter"


def test_list_disposition_filter_values_accepted():
    """Valid disposition filters must not 422 (empty result ok with mocked empty query)."""

    async def _exec(_stmt):
        result = MagicMock()
        result.scalar_one.return_value = 0
        result.all.return_value = []
        return result

    db = AsyncMock()
    db.execute = AsyncMock(side_effect=_exec)

    async def fake_db():
        yield db

    app.dependency_overrides[get_db] = fake_db
    for value in ("parked", "excluded", "set", "unset"):
        r = client.get(f"/api/v1/distributors?disposition={value}")
        assert r.status_code == 200, value
        assert r.json()["total"] == 0
