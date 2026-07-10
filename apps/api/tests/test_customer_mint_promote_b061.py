"""BACKLOG-061-U2b — mint mode on bulk promote (no cip writes)."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient

from app.api.deps import get_db
from app.main import app
from app.services.customer_bulk_promote import BATCH_MAX_ROWS, run_customer_bulk_promote
from app.services.customer_code_mint import render_customer_code
from app.services.customer_promote import PROMOTE_TARGET_STATUS

client = TestClient(app)


def setup_function():
    app.dependency_overrides.clear()


def teardown_function():
    app.dependency_overrides.clear()


def _row(**kwargs):
    base = dict(
        id=10,
        code="TMP-CUST-ABC",
        name="Acme",
        customer_status="unverified",
        merged_into_customer_id=None,
        notes_summary=None,
    )
    base.update(kwargs)
    return SimpleNamespace(**base)


def _settings(**kwargs):
    base = dict(
        tenant_id="default",
        pattern_template="{PREFIX}{SEP}{SEQ}",
        prefix="CUST",
        separator="-",
        pad_width=6,
        segment_mode="none",
        next_seq=1,
        updated_at=None,
    )
    base.update(kwargs)
    return SimpleNamespace(**base)


def _db_for_batch(rows_by_code: dict[str, SimpleNamespace], owners_by_new: dict[str, SimpleNamespace] | None = None):
    """Same shape as BP1 tests — resolve TMP / collision by lower(code)."""
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
            if key.startswith("tmp-cust-"):
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
            if key and not key.startswith("tmp-cust-")
            else None
        )
        # For id-only existence: return id when occupied
        if key and not key.startswith("tmp-cust-"):
            if found is not None:
                result.scalar_one_or_none.return_value = found.id
            elif key in {c.lower() for c in owners_by_new}:
                result.scalar_one_or_none.return_value = 1
            else:
                # check occupied via owners keys only
                result.scalar_one_or_none.return_value = None
        return result

    db.execute = AsyncMock(side_effect=_exec)
    db.commit = AsyncMock()
    db.refresh = AsyncMock()
    db.flush = AsyncMock()
    db.add = MagicMock()
    return db


def _patch_mint(settings: SimpleNamespace, occupied: set[str] | None = None):
    """Patch allocator helpers so tests don't need a settings-table mock."""
    occupied_l = {c.lower() for c in (occupied or set())}
    seq_box = {"n": int(settings.next_seq)}

    async def _fake_mint(db, *, tenant_id="default", dry_run=False, reserved=None, start_seq=None):
        from app.services.customer_code_mint import render_customer_code as render
        from app.services.customer_promote import CustomerPromoteError

        if (settings.segment_mode or "").lower() != "none":
            raise CustomerPromoteError(
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
        raise CustomerPromoteError("exhausted", status_code=503, code="mint_exhausted")

    return patch(
        "app.services.customer_bulk_promote.mint_next_customer_code",
        side_effect=_fake_mint,
    )


def test_render_candidate_a():
    assert render_customer_code(prefix="CUST", separator="-", seq=1, pad_width=6) == "CUST-000001"
    assert render_customer_code(prefix="CUST", separator="-", seq=1001, pad_width=6) == "CUST-001001"


def test_mint_dry_run_previews_without_advancing_next_seq():
    a = _row(id=10, code="TMP-CUST-A")
    b = _row(id=11, code="TMP-CUST-B")
    db = _db_for_batch({"TMP-CUST-A": a, "TMP-CUST-B": b})
    settings = _settings()
    with _patch_mint(settings):
        out = asyncio.run(
            run_customer_bulk_promote(
                db,
                rows=[{"tmp_code": "TMP-CUST-A"}, {"tmp_code": "TMP-CUST-B"}],
                dry_run=True,
                mode="mint",
            )
        )
    assert out["mode"] == "mint"
    assert out["summary"]["ready"] == 2
    assert out["rows"][0]["new_code"] == "CUST-000001"
    assert out["rows"][1]["new_code"] == "CUST-000002"
    assert settings.next_seq == 1
    assert a.code == "TMP-CUST-A"


def test_mint_confirm_advances_next_seq():
    a = _row(id=10, code="TMP-CUST-A")
    b = _row(id=11, code="TMP-CUST-B")
    db = _db_for_batch({"TMP-CUST-A": a, "TMP-CUST-B": b})
    settings = _settings()
    with _patch_mint(settings):
        out = asyncio.run(
            run_customer_bulk_promote(
                db,
                rows=[{"tmp_code": "TMP-CUST-A"}, {"tmp_code": "TMP-CUST-B"}],
                dry_run=False,
                mode="mint",
            )
        )
    assert out["summary"]["applied"] == 2
    assert a.code == "CUST-000001"
    assert b.code == "CUST-000002"
    assert a.customer_status == PROMOTE_TARGET_STATUS
    assert settings.next_seq == 3


def test_mint_silent_bump_past_occupied():
    a = _row(id=10, code="TMP-CUST-A")
    b = _row(id=11, code="TMP-CUST-B")
    db = _db_for_batch({"TMP-CUST-A": a, "TMP-CUST-B": b})
    settings = _settings()
    with _patch_mint(settings, occupied={"CUST-000002"}):
        out = asyncio.run(
            run_customer_bulk_promote(
                db,
                rows=[{"tmp_code": "TMP-CUST-A"}, {"tmp_code": "TMP-CUST-B"}],
                dry_run=False,
                mode="mint",
            )
        )
    assert out["summary"]["applied"] == 2
    assert a.code == "CUST-000001"
    assert b.code == "CUST-000003"
    assert settings.next_seq == 4


def test_cust_1001_does_not_collide_with_padded_mints():
    a = _row(id=10, code="TMP-CUST-A")
    db = _db_for_batch({"TMP-CUST-A": a})
    settings = _settings(next_seq=1001)
    with _patch_mint(settings, occupied={"CUST-1001"}):
        out = asyncio.run(
            run_customer_bulk_promote(
                db,
                rows=[{"tmp_code": "TMP-CUST-A"}],
                dry_run=False,
                mode="mint",
            )
        )
    assert out["summary"]["applied"] == 1
    assert a.code == "CUST-001001"
    assert settings.next_seq == 1002


def test_map_mode_unchanged_blank_skip():
    row = _row()
    db = _db_for_batch({"TMP-CUST-ABC": row})
    out = asyncio.run(
        run_customer_bulk_promote(
            db,
            rows=[
                {"tmp_code": "TMP-CUST-ABC", "new_code": "ACME-001"},
                {"tmp_code": "TMP-CUST-NOPE", "new_code": ""},
            ],
            dry_run=True,
            mode="map",
        )
    )
    assert out["mode"] == "map"
    assert out["summary"]["ready"] == 1
    assert out["summary"]["skipped"] == 1
    assert out["rows"][0]["status"] == "ready"


def test_mint_rejects_provided_new_code():
    row = _row()
    db = _db_for_batch({"TMP-CUST-ABC": row})
    settings = _settings()
    with _patch_mint(settings):
        out = asyncio.run(
            run_customer_bulk_promote(
                db,
                rows=[{"tmp_code": "TMP-CUST-ABC", "new_code": "SHOULD-NOT"}],
                dry_run=True,
                mode="mint",
            )
        )
    assert out["rows"][0]["status"] == "blocked"
    assert "new_code_not_allowed_in_mint" in out["rows"][0]["reasons"]


def test_mint_duplicate_tmp_blocks_both():
    a = _row(id=10, code="TMP-CUST-A")
    db = _db_for_batch({"TMP-CUST-A": a})
    settings = _settings()
    with _patch_mint(settings):
        out = asyncio.run(
            run_customer_bulk_promote(
                db,
                rows=[{"tmp_code": "TMP-CUST-A"}, {"tmp_code": "TMP-CUST-A"}],
                dry_run=True,
                mode="mint",
            )
        )
    assert out["summary"]["blocked"] == 2
    assert all("intra_batch_duplicate_tmp" in r["reasons"] for r in out["rows"])


def test_mint_batch_too_large_http():
    async def fake_db():
        yield AsyncMock()

    app.dependency_overrides[get_db] = fake_db
    rows = [{"tmp_code": f"TMP-CUST-{i}"} for i in range(BATCH_MAX_ROWS + 1)]
    r = client.post(
        "/api/v1/customers/promote/batch",
        json={"rows": rows, "dry_run": True, "mode": "mint"},
    )
    assert r.status_code == 422
    assert r.json()["detail"]["code"] == "batch_too_large"


def test_mint_partial_success():
    a = _row(id=10, code="TMP-CUST-A")
    b = _row(id=11, code="TMP-CUST-B", customer_status="merged", merged_into_customer_id=99)
    db = _db_for_batch({"TMP-CUST-A": a, "TMP-CUST-B": b})
    settings = _settings()
    with _patch_mint(settings):
        out = asyncio.run(
            run_customer_bulk_promote(
                db,
                rows=[{"tmp_code": "TMP-CUST-A"}, {"tmp_code": "TMP-CUST-B"}],
                dry_run=False,
                mode="mint",
            )
        )
    assert out["summary"]["applied"] == 1
    assert out["summary"]["blocked"] == 1
    assert a.code == "CUST-000001"
    assert b.code == "TMP-CUST-B"
    assert settings.next_seq >= 2


def test_segment_mode_unsupported():
    a = _row(id=10, code="TMP-CUST-A")
    db = _db_for_batch({"TMP-CUST-A": a})
    settings = _settings(segment_mode="region")
    with _patch_mint(settings):
        out = asyncio.run(
            run_customer_bulk_promote(
                db,
                rows=[{"tmp_code": "TMP-CUST-A"}],
                dry_run=True,
                mode="mint",
            )
        )
    assert out["rows"][0]["status"] == "blocked"
    assert "mint_segment_mode_unsupported" in out["rows"][0]["reasons"]
