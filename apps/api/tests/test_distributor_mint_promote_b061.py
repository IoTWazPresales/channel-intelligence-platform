"""BACKLOG-061-U-B3a — mint mode on distributor bulk promote (no cip writes)."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient

from app.api.deps import get_db
from app.main import app
from app.services.distributor_bulk_promote import run_distributor_bulk_promote
from app.services.distributor_code_mint import render_distributor_code
from app.services.distributor_promote import PROMOTE_TARGET_STATUS

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


def _settings(**kwargs):
    base = dict(
        tenant_id="default",
        pattern_template="{PREFIX}{SEP}{SEQ}",
        prefix="DIST",
        separator="-",
        pad_width=6,
        segment_mode="none",
        next_seq=1,
        updated_at=None,
    )
    base.update(kwargs)
    return SimpleNamespace(**base)


def _db_for_batch(rows_by_code: dict[str, SimpleNamespace], owners_by_new: dict[str, SimpleNamespace] | None = None):
    owners_by_new = owners_by_new or {}
    by_id = {int(r.id): r for r in rows_by_code.values()}
    db = AsyncMock()

    async def _get(_cls, pk):
        return by_id.get(int(pk))

    db.get = AsyncMock(side_effect=_get)

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

        found = None
        if key:
            if key.startswith("tmp-dist-"):
                for code, row in rows_by_code.items():
                    if code.lower() == key:
                        found = row
                        break
            else:
                for code, row in owners_by_new.items():
                    if code.lower() == key:
                        found = row
                        break
                if found is None:
                    for row in by_id.values():
                        if str(row.code).lower() == key:
                            found = row
                            break
        result.scalars.return_value.first.return_value = found
        result.scalar_one_or_none.return_value = (
            (found.id if found is not None else None)
            if key and not key.startswith("tmp-dist-")
            else None
        )
        if key and not key.startswith("tmp-dist-"):
            if found is not None:
                result.scalar_one_or_none.return_value = found.id
            else:
                result.scalar_one_or_none.return_value = None
        return result

    db.execute = AsyncMock(side_effect=_exec)
    db.commit = AsyncMock()
    db.refresh = AsyncMock()
    db.flush = AsyncMock()
    db.add = MagicMock()
    return db


def _patch_mint(settings: SimpleNamespace, occupied: set[str] | None = None):
    occupied_l = {c.lower() for c in (occupied or set())}
    seq_box = {"n": int(settings.next_seq)}

    async def _fake_mint(db, *, tenant_id="default", dry_run=False, reserved=None, start_seq=None):
        from app.services.distributor_code_mint import render_distributor_code as render
        from app.services.distributor_promote import DistributorPromoteError

        if (settings.segment_mode or "").lower() != "none":
            raise DistributorPromoteError(
                "segment unsupported",
                status_code=422,
                code="mint_segment_mode_unsupported",
            )
        reserved = reserved or set()
        seq = int(start_seq) if start_seq is not None else seq_box["n"]
        for _ in range(10000):
            code = render(
                prefix=settings.prefix,
                separator=settings.separator,
                seq=seq,
                pad_width=settings.pad_width,
            )
            if code.lower() not in occupied_l and code.lower() not in reserved:
                if not dry_run:
                    seq_box["n"] = seq + 1
                    settings.next_seq = seq + 1
                return code, seq
            seq += 1
        raise DistributorPromoteError("exhausted", status_code=503, code="mint_exhausted")

    return patch(
        "app.services.distributor_bulk_promote.mint_next_distributor_code",
        side_effect=_fake_mint,
    )


def test_render_dist_candidate_a():
    assert render_distributor_code(prefix="DIST", separator="-", seq=1, pad_width=6) == "DIST-000001"
    assert render_distributor_code(prefix="DIST", separator="-", seq=1001, pad_width=6) == "DIST-001001"


def test_mint_dry_run_previews_without_advancing_next_seq():
    a = _row(id=10, code="TMP-DIST-A")
    b = _row(id=11, code="TMP-DIST-B")
    db = _db_for_batch({"TMP-DIST-A": a, "TMP-DIST-B": b})
    settings = _settings()
    with _patch_mint(settings):
        out = asyncio.run(
            run_distributor_bulk_promote(
                db,
                rows=[{"tmp_code": "TMP-DIST-A"}, {"tmp_code": "TMP-DIST-B"}],
                dry_run=True,
                mode="mint",
            )
        )
    assert out["mode"] == "mint"
    assert out["summary"]["ready"] == 2
    assert out["rows"][0]["new_code"] == "DIST-000001"
    assert out["rows"][1]["new_code"] == "DIST-000002"
    assert settings.next_seq == 1
    assert a.code == "TMP-DIST-A"


def test_mint_confirm_advances_seq():
    a = _row(id=10, code="TMP-DIST-A")
    b = _row(id=11, code="TMP-DIST-B")
    db = _db_for_batch({"TMP-DIST-A": a, "TMP-DIST-B": b})
    settings = _settings()
    with _patch_mint(settings):
        out = asyncio.run(
            run_distributor_bulk_promote(
                db,
                rows=[{"tmp_code": "TMP-DIST-A"}, {"tmp_code": "TMP-DIST-B"}],
                dry_run=False,
                mode="mint",
            )
        )
    assert out["summary"]["applied"] == 2
    assert a.code == "DIST-000001"
    assert b.code == "DIST-000002"
    assert a.distributor_status == PROMOTE_TARGET_STATUS
    assert settings.next_seq == 3


def test_mint_silent_bump_past_occupied():
    a = _row(id=10, code="TMP-DIST-A")
    b = _row(id=11, code="TMP-DIST-B")
    db = _db_for_batch({"TMP-DIST-A": a, "TMP-DIST-B": b})
    settings = _settings()
    with _patch_mint(settings, occupied={"DIST-000002"}):
        out = asyncio.run(
            run_distributor_bulk_promote(
                db,
                rows=[{"tmp_code": "TMP-DIST-A"}, {"tmp_code": "TMP-DIST-B"}],
                dry_run=False,
                mode="mint",
            )
        )
    assert out["summary"]["applied"] == 2
    assert a.code == "DIST-000001"
    assert b.code == "DIST-000003"
    assert settings.next_seq == 4


def test_mint_rejects_provided_new_code():
    row = _row()
    db = _db_for_batch({"TMP-DIST-ABC": row})
    settings = _settings()
    with _patch_mint(settings):
        out = asyncio.run(
            run_distributor_bulk_promote(
                db,
                rows=[{"tmp_code": "TMP-DIST-ABC", "new_code": "SHOULD-NOT"}],
                dry_run=True,
                mode="mint",
            )
        )
    assert out["rows"][0]["status"] == "blocked"
    assert "new_code_not_allowed_in_mint" in out["rows"][0]["reasons"]
    assert settings.next_seq == 1


def test_http_mint_dry_run():
    row = _row()

    async def fake_db():
        yield _db_for_batch({"TMP-DIST-ABC": row})

    app.dependency_overrides[get_db] = fake_db
    settings = _settings()
    with _patch_mint(settings):
        r = client.post(
            "/api/v1/distributors/promote/batch",
            json={"dry_run": True, "mode": "mint", "rows": [{"tmp_code": "TMP-DIST-ABC"}]},
        )
    assert r.status_code == 200
    body = r.json()
    assert body["mode"] == "mint"
    assert body["summary"]["ready"] == 1
    assert body["rows"][0]["new_code"] == "DIST-000001"
    assert row.code == "TMP-DIST-ABC"
