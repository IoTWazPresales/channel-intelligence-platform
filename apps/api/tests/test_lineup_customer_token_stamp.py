"""Unit 6b — customer-token stamp helpers + DB integration (ALLOW_TESTS_ON_DEV_DB=1)."""

from __future__ import annotations

import secrets

import pytest
from sqlalchemy import delete, select

from app.services.commercial_planner.lineup_customer_token_stamp import (
    CONFLICT_DISPOSITIONS,
    CustomerTokenConflictError,
    CustomerTokenStampError,
    apply_customer_token_stamp,
    preview_customer_token_stamp,
    revoke_customer_token_alias,
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
    assert "**Closed**" in text.split("BACKLOG-124", 1)[1].split("## BACKLOG-", 1)[0]


@pytest.mark.anyio
async def test_tokenless_stamp_sets_customer_id_no_alias():
    from app.db.session import AsyncSessionLocal
    from app.models.commercial_lineup import CommercialLineupCase, CommercialLineupLine
    from app.models.import_distributor_si import CustomerSourceTokenAlias
    from app.models.steward_audit import StewardAuditEvent
    from app.services.commercial_planner.lineup_tokenless_customer_stamp import (
        apply_tokenless_customer_stamp,
        preview_tokenless_customer_stamp,
    )

    async with AsyncSessionLocal() as db:
        c1, _, _ = await _two_named_customers(db)
        case_id = (await db.execute(select(CommercialLineupCase.id).limit(1))).scalar_one_or_none()
        if case_id is None:
            pytest.skip("no commercial_lineup_case")
        lines = []
        for i in range(2):
            ln = CommercialLineupLine(
                case_id=int(case_id),
                customer_token=None,
                customer_id=None,
                row_status="imported",
                diagnostic_codes=["unknown_customer"],
                source_row_number=9100 + i,
            )
            db.add(ln)
            lines.append(ln)
        await db.commit()
        for ln in lines:
            await db.refresh(ln)
        line_ids = [int(ln.id) for ln in lines]
        try:
            prev = await preview_tokenless_customer_stamp(
                db, line_ids=line_ids, target_customer_id=c1
            )
            assert prev["line_count"] == 2
            assert prev["mints_alias"] is False
            assert prev["writes_customer_token"] is False

            out = await apply_tokenless_customer_stamp(
                db,
                {"display_name": "b124-test"},
                line_ids=line_ids,
                target_customer_id=c1,
                reason="b124 tokenless proof",
            )
            assert out["stamped_count"] == 2
            assert out["mints_alias"] is False
            for lid in line_ids:
                ln = await db.get(CommercialLineupLine, lid)
                assert ln is not None
                assert int(ln.customer_id) == c1
                assert not (ln.customer_token or "").strip()

            # Mechanism D must not mint an alias for blank tokens
            blank_alias = (
                await db.execute(
                    select(CustomerSourceTokenAlias).where(
                        CustomerSourceTokenAlias.normalized_token == "",
                        CustomerSourceTokenAlias.status == "approved",
                    )
                )
            ).scalars().first()
            assert blank_alias is None

            audits = list(
                (
                    await db.execute(
                        select(StewardAuditEvent).where(
                            StewardAuditEvent.action == "lineup_tokenless_customer_stamp",
                        )
                    )
                ).scalars().all()
            )
            assert any(
                set(a.payload_json.get("line_ids") or []) == set(line_ids) for a in audits
            )
        finally:
            await db.execute(delete(CommercialLineupLine).where(CommercialLineupLine.id.in_(line_ids)))
            await db.commit()


@pytest.mark.anyio
async def test_tokenless_rejects_non_blank_token_lines():
    from app.db.session import AsyncSessionLocal
    from app.services.commercial_planner.lineup_tokenless_customer_stamp import (
        preview_tokenless_customer_stamp,
    )

    async with AsyncSessionLocal() as db:
        c1, _, _ = await _two_named_customers(db)
        tok = f"unit6b-not-empty-{secrets.token_hex(4)}"
        lines = await _seed_token_lines(db, norm_token=tok, n=1)
        line_ids = [int(ln.id) for ln in lines]
        try:
            prev = await preview_tokenless_customer_stamp(
                db, line_ids=line_ids, target_customer_id=c1
            )
            assert prev["line_count"] == 0
            assert prev["rejected_count"] == 1
            assert prev["rejected"][0]["reason"] == "customer_token_not_blank"
        finally:
            await _cleanup(db, line_ids=line_ids, alias_ids=[], norm_token=tok)


@pytest.mark.anyio
async def test_worklist_empty_token_per_case_stampable():
    from app.db.session import AsyncSessionLocal
    from app.models.commercial_lineup import CommercialLineupCase, CommercialLineupLine
    from app.services.commercial_planner.lineup_customer_token_stamp import (
        list_customer_token_worklist,
    )

    async with AsyncSessionLocal() as db:
        case_id = (await db.execute(select(CommercialLineupCase.id).limit(1))).scalar_one_or_none()
        if case_id is None:
            pytest.skip("no commercial_lineup_case")
        ln = CommercialLineupLine(
            case_id=int(case_id),
            customer_token="",
            customer_id=None,
            row_status="imported",
            diagnostic_codes=["unknown_customer"],
            source_row_number=9200,
        )
        db.add(ln)
        await db.commit()
        await db.refresh(ln)
        try:
            wl = await list_customer_token_worklist(db, limit=500)
            hits = [
                it
                for it in wl["items"]
                if it.get("bucket") == "empty_token" and int(it.get("case_id") or 0) == int(case_id)
            ]
            assert hits, "expected empty_token worklist item for seeded case"
            hit = next((h for h in hits if int(ln.id) in (h.get("line_ids") or [])), hits[0])
            assert hit["tokenless"] is True
            assert hit["stamp_enabled"] is True
            assert hit["preferred_target_id"] is None
            assert hit["free_target_allowed"] is True
            assert int(ln.id) in hit["line_ids"]
            assert wl["bucket_counts"].get("empty_token", 0) >= 1
        finally:
            await db.execute(delete(CommercialLineupLine).where(CommercialLineupLine.id == int(ln.id)))
            await db.commit()


async def _two_named_customers(db):
    from app.models.dimensions import DimCustomer
    from app.services.commercial_planner.open_channel_customer import get_open_channel_customer_id

    oc = await get_open_channel_customer_id(db)
    rows = list(
        (
            await db.execute(
                select(DimCustomer.id).where(DimCustomer.id != (oc or -1)).order_by(DimCustomer.id).limit(2)
            )
        ).scalars().all()
    )
    if len(rows) < 2:
        pytest.skip("need ≥2 non–OPEN_CHANNEL customers")
    return int(rows[0]), int(rows[1]), oc


async def _seed_token_lines(db, *, norm_token: str, n: int = 2):
    from app.models.commercial_lineup import CommercialLineupCase, CommercialLineupLine

    case_id = (await db.execute(select(CommercialLineupCase.id).limit(1))).scalar_one_or_none()
    if case_id is None:
        pytest.skip("no commercial_lineup_case")
    lines = []
    for i in range(n):
        ln = CommercialLineupLine(
            case_id=int(case_id),
            customer_token=norm_token,
            customer_id=None,
            row_status="imported",
            diagnostic_codes=["unknown_customer"],
            source_row_number=9000 + i,
        )
        db.add(ln)
        lines.append(ln)
    await db.commit()
    for ln in lines:
        await db.refresh(ln)
    return lines


async def _cleanup(db, *, line_ids: list[int], alias_ids: list[int], norm_token: str):
    from app.models.commercial_lineup import CommercialLineupLine
    from app.models.import_distributor_si import CustomerSourceTokenAlias

    if line_ids:
        await db.execute(delete(CommercialLineupLine).where(CommercialLineupLine.id.in_(line_ids)))
    if alias_ids:
        await db.execute(
            delete(CustomerSourceTokenAlias).where(CustomerSourceTokenAlias.id.in_(alias_ids))
        )
    await db.execute(
        delete(CustomerSourceTokenAlias).where(
            CustomerSourceTokenAlias.normalized_token == norm_token
        )
    )
    # steward_audit_event: cip role may lack DELETE — leave token-scoped audit rows
    await db.commit()


@pytest.mark.anyio
async def test_preview_no_writes_and_empty_token_rejected():
    from app.db.session import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        with pytest.raises(CustomerTokenStampError, match="empty token"):
            await preview_customer_token_stamp(db, norm_token="   ", target_customer_id=1)

        tok = f"unit6b-preview-{secrets.token_hex(4)}"
        c1, _, _ = await _two_named_customers(db)
        lines = await _seed_token_lines(db, norm_token=tok, n=2)
        line_ids = [int(ln.id) for ln in lines]
        try:
            prev = await preview_customer_token_stamp(
                db, norm_token=tok, target_customer_id=c1
            )
            assert prev["line_count"] == 2
            assert prev["would_create_alias"] is True
            # still null on lines
            for lid in line_ids:
                row = await db.get(
                    __import__(
                        "app.models.commercial_lineup", fromlist=["CommercialLineupLine"]
                    ).CommercialLineupLine,
                    lid,
                )
                assert row is not None and row.customer_id is None
        finally:
            await _cleanup(db, line_ids=line_ids, alias_ids=[], norm_token=tok)


@pytest.mark.anyio
async def test_apply_mints_alias_stamps_lines_one_audit():
    from app.db.session import AsyncSessionLocal
    from app.models.import_distributor_si import CustomerSourceTokenAlias
    from app.models.steward_audit import StewardAuditEvent

    async with AsyncSessionLocal() as db:
        tok = f"unit6b-apply-{secrets.token_hex(4)}"
        c1, _, _ = await _two_named_customers(db)
        lines = await _seed_token_lines(db, norm_token=tok, n=2)
        line_ids = [int(ln.id) for ln in lines]
        alias_ids: list[int] = []
        try:
            out = await apply_customer_token_stamp(
                db,
                {"display_name": "unit6b-test"},
                norm_token=tok,
                target_customer_id=c1,
                reason="unit6b apply proof",
            )
            assert out["stamped_count"] == 2
            alias_ids.append(int(out["alias_id"]))
            alias = await db.get(CustomerSourceTokenAlias, out["alias_id"])
            assert alias is not None
            assert alias.status == "approved"
            assert alias.source_definition_id is None
            assert alias.distributor_id is None
            assert int(alias.customer_id) == c1

            from app.models.commercial_lineup import CommercialLineupLine

            for lid in line_ids:
                ln = await db.get(CommercialLineupLine, lid)
                assert ln is not None and int(ln.customer_id) == c1

            audits = list(
                (
                    await db.execute(
                        select(StewardAuditEvent).where(
                            StewardAuditEvent.action == "lineup_customer_token_stamp",
                            StewardAuditEvent.entity_token == tok,
                        )
                    )
                ).scalars().all()
            )
            assert len(audits) == 1
            assert audits[0].payload_json["alias_id"] == out["alias_id"]
        finally:
            await _cleanup(db, line_ids=line_ids, alias_ids=alias_ids, norm_token=tok)


@pytest.mark.anyio
async def test_apply_rollback_when_audit_raises():
    from unittest.mock import AsyncMock, patch

    from app.db.session import AsyncSessionLocal
    from app.models.commercial_lineup import CommercialLineupLine
    from app.models.import_distributor_si import CustomerSourceTokenAlias

    async with AsyncSessionLocal() as db:
        tok = f"unit6b-rollback-{secrets.token_hex(4)}"
        c1, _, _ = await _two_named_customers(db)
        lines = await _seed_token_lines(db, norm_token=tok, n=1)
        line_ids = [int(ln.id) for ln in lines]
        try:
            with patch(
                "app.services.commercial_planner.lineup_customer_token_stamp.record_steward_audit",
                new=AsyncMock(side_effect=RuntimeError("forced audit failure")),
            ):
                with pytest.raises(RuntimeError, match="forced audit failure"):
                    await apply_customer_token_stamp(
                        db,
                        None,
                        norm_token=tok,
                        target_customer_id=c1,
                        reason="should roll back",
                    )
            await db.rollback()
            # No approved global alias for token
            alias = (
                await db.execute(
                    select(CustomerSourceTokenAlias).where(
                        CustomerSourceTokenAlias.normalized_token == tok,
                        CustomerSourceTokenAlias.status == "approved",
                    )
                )
            ).scalars().first()
            assert alias is None
            ln = await db.get(CommercialLineupLine, line_ids[0])
            assert ln is not None and ln.customer_id is None
        finally:
            await _cleanup(db, line_ids=line_ids, alias_ids=[], norm_token=tok)


@pytest.mark.anyio
async def test_genuine_conflict_writes_nothing():
    from app.db.session import AsyncSessionLocal
    from app.models.commercial_lineup import CommercialLineupLine
    from app.models.dimensions import DimDistributor
    from app.models.import_distributor_si import CustomerSourceTokenAlias

    async with AsyncSessionLocal() as db:
        tok = f"unit6b-conflict-{secrets.token_hex(4)}"
        c1, c2, _ = await _two_named_customers(db)
        dists = list(
            (
                await db.execute(select(DimDistributor.id).order_by(DimDistributor.id).limit(2))
            ).scalars().all()
        )
        if len(dists) < 2:
            pytest.skip("need ≥2 distributors for scoped conflict aliases")
        # Two distributor-scoped approved aliases → named competitors (valid FKs)
        a1 = CustomerSourceTokenAlias(
            customer_id=c1,
            source_definition_id=None,
            distributor_id=int(dists[0]),
            raw_token=tok,
            normalized_token=tok,
            status="approved",
            notes="unit6b conflict seed a",
        )
        a2 = CustomerSourceTokenAlias(
            customer_id=c2,
            source_definition_id=None,
            distributor_id=int(dists[1]),
            raw_token=tok,
            normalized_token=tok,
            status="approved",
            notes="unit6b conflict seed b",
        )
        db.add_all([a1, a2])
        await db.commit()
        await db.refresh(a1)
        await db.refresh(a2)
        seed_alias_ids = [int(a1.id), int(a2.id)]
        lines = await _seed_token_lines(db, norm_token=tok, n=1)
        line_ids = [int(ln.id) for ln in lines]
        try:
            with pytest.raises(CustomerTokenConflictError) as ei:
                await apply_customer_token_stamp(
                    db,
                    None,
                    norm_token=tok,
                    target_customer_id=c1,
                    reason="must refuse",
                )
            assert sorted(ei.value.competing_customer_ids) == sorted([c1, c2])
            await db.rollback()
            ln = await db.get(CommercialLineupLine, line_ids[0])
            assert ln is not None and ln.customer_id is None
            global_alias = (
                await db.execute(
                    select(CustomerSourceTokenAlias).where(
                        CustomerSourceTokenAlias.normalized_token == tok,
                        CustomerSourceTokenAlias.source_definition_id.is_(None),
                        CustomerSourceTokenAlias.distributor_id.is_(None),
                    )
                )
            ).scalars().first()
            assert global_alias is None
        finally:
            await _cleanup(
                db,
                line_ids=line_ids,
                alias_ids=seed_alias_ids,
                norm_token=tok,
            )


@pytest.mark.anyio
async def test_revoke_unwinds_stamped_lines():
    from app.db.session import AsyncSessionLocal
    from app.models.commercial_lineup import CommercialLineupLine
    from app.models.import_distributor_si import CustomerSourceTokenAlias

    async with AsyncSessionLocal() as db:
        tok = f"unit6b-revoke-{secrets.token_hex(4)}"
        c1, _, _ = await _two_named_customers(db)
        lines = await _seed_token_lines(db, norm_token=tok, n=2)
        line_ids = [int(ln.id) for ln in lines]
        alias_ids: list[int] = []
        try:
            out = await apply_customer_token_stamp(
                db,
                {"display_name": "unit6b-revoke"},
                norm_token=tok,
                target_customer_id=c1,
                reason="stamp then revoke",
            )
            alias_ids.append(int(out["alias_id"]))
            rev = await revoke_customer_token_alias(
                db,
                {"display_name": "unit6b-revoke"},
                alias_id=int(out["alias_id"]),
                reason="unit6b revoke proof",
            )
            assert rev["status"] == "revoked"
            assert rev["unwound_count"] > 0
            alias = await db.get(CustomerSourceTokenAlias, out["alias_id"])
            assert alias is not None and alias.status == "revoked"
            for lid in line_ids:
                ln = await db.get(CommercialLineupLine, lid)
                assert ln is not None and ln.customer_id is None
        finally:
            await _cleanup(db, line_ids=line_ids, alias_ids=alias_ids, norm_token=tok)
