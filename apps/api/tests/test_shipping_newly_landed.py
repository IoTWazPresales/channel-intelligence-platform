"""SH-04 newly landed + shared observation LAG (BACKLOG-132 Unit A)."""

from __future__ import annotations

import asyncio
import hashlib
import os
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest
from sqlalchemy import select

from app.db.session import AsyncSessionLocal
from app.db.session_sync import SessionLocal
from app.models.ingestion import ImportJob, SourceDefinition
from app.models.shipment_evidence import ShipmentEvidenceLine
from app.models.shipment_evidence_observation import ShipmentEvidenceObservation
from app.services.shipping.newly_landed import newly_landed_transitions
from app.services.shipping.observation_transitions import (
    LINE_COLUMN_KEYS,
    PUBLIC_ETA_SHIFT_SAMPLE_CAP,
    PUBLIC_ETA_SHIFT_SAMPLE_KEYS,
    compute_eta_shifts,
    identity_scope_for_job,
    observation_field_lag,
)


def _sqlalchemy_db_name(url: str) -> str:
    if not url or "://" not in url:
        return ""
    rest = url.split("://", 1)[1]
    if "/" not in rest:
        return ""
    db = rest.rsplit("/", 1)[-1]
    return db.split("?", 1)[0].strip()


def _skip_mutations_on_shared_cip() -> None:
    if os.environ.get("ALLOW_TESTS_ON_DEV_DB", "").strip() == "1":
        return
    from app.core.config import get_settings

    settings = get_settings()
    if _sqlalchemy_db_name(settings.database_url) == "cip" or _sqlalchemy_db_name(
        settings.database_url_sync
    ) == "cip":
        pytest.skip("Set ALLOW_TESTS_ON_DEV_DB=1 for newly-landed DB tests on cip")


def _hash(*parts: str) -> str:
    return hashlib.sha1("|".join(parts).encode("utf-8")).hexdigest()


def test_public_eta_shift_contract_constants() -> None:
    assert PUBLIC_ETA_SHIFT_SAMPLE_CAP == 50
    assert "source_key" in PUBLIC_ETA_SHIFT_SAMPLE_KEYS
    assert "distributor" not in PUBLIC_ETA_SHIFT_SAMPLE_KEYS


def test_observation_field_lag_is_window() -> None:
    expr = observation_field_lag(ShipmentEvidenceObservation.pod_date)
    sql = str(expr)
    assert "lag" in sql.lower()


def test_newly_landed_module_uses_shared_lag_not_landed_week() -> None:
    src = Path(__file__).resolve().parents[1] / "app" / "services" / "shipping" / "newly_landed.py"
    text = src.read_text(encoding="utf-8")
    assert "observation_lag_window" in text
    assert "predicate_landed_week" not in text
    assert "require_current_incoming=True" not in text


def test_sh04_documented() -> None:
    doc = Path(__file__).resolve().parents[3] / "docs" / "COMMERCIAL_SEMANTICS.md"
    text = doc.read_text(encoding="utf-8")
    assert "SH-04" in text
    assert "Newly POD'd since prior report" in text
    assert "landed_week" in text


def _make_job(db, src_id: int, name: str) -> ImportJob:
    job = ImportJob(
        source_id=src_id,
        template_slug="inbound_shipments",
        status="loaded",
        file_name=name,
        created_at=datetime.now(timezone.utc),
        completed_at=datetime.now(timezone.utc),
    )
    db.add(job)
    db.flush()
    return job


def _make_line(db, job_id: int, source_key: str, row: int) -> ShipmentEvidenceLine:
    line = ShipmentEvidenceLine(
        import_job_id=job_id,
        source_key=source_key,
        source_row_number=row,
        report_type="xxomrpt0027_order",
        line_state="shipped",
        raw_source_row={"test": "b132"},
        product_resolution_status="resolved_unique",
        distributor_resolution_status="resolved",
        sales_model_name="UX3402VA",
        quantity=2,
        bill_to_raw="Mustek",
        customer_dealer_token="GAME-SA",
    )
    db.add(line)
    db.flush()
    return line


def _make_obs(
    db,
    *,
    job_id: int,
    line_id: int,
    identity: str,
    source_key: str,
    row_hash: str,
    valid_from: datetime,
    pod: date | None,
    est_pod: date | None = None,
    promise: date | None = None,
) -> ShipmentEvidenceObservation:
    obs = ShipmentEvidenceObservation(
        line_identity_key=identity,
        import_job_id=job_id,
        source_key=source_key,
        source_row_hash=row_hash,
        evidence_line_id=line_id,
        valid_from=valid_from,
        observed_at=valid_from,
        source_row_number=1,
        report_type="xxomrpt0027_order",
        line_state="shipped",
        raw_source_row={"test": "b132"},
        product_resolution_status="resolved_unique",
        distributor_resolution_status="resolved",
        sales_model_name="UX3402VA",
        quantity=2,
        bill_to_raw="Mustek",
        customer_dealer_token="GAME-SA",
        pod_date=pod,
        est_pod_date=est_pod,
        promise_date=promise,
    )
    db.add(obs)
    db.flush()
    return obs


def _run(coro):
    return asyncio.run(coro)


async def _newly(job_id: int) -> dict:
    async with AsyncSessionLocal() as db:
        return await newly_landed_transitions(db, import_job_id=job_id, with_line_columns=True)


def test_newly_landed_null_to_set_only() -> None:
    _skip_mutations_on_shared_cip()
    t0 = datetime(2026, 8, 1, tzinfo=timezone.utc)
    t1 = t0 + timedelta(days=7)
    job_ids: list[int] = []
    with SessionLocal() as db:
        src = db.scalar(select(SourceDefinition).limit(1))
        if src is None:
            pytest.skip("no source_definition row")
        sid = int(src.id)
        job_a = _make_job(db, sid, "b132-nl-a.csv")
        job_b = _make_job(db, sid, "b132-nl-b.csv")
        job_ids = [int(job_a.id), int(job_b.id)]

        # NULL → set : one row
        sk1 = "b132:nl:hit"
        id1 = "b132:ident:hit"
        la = _make_line(db, int(job_a.id), sk1, 1)
        lb = _make_line(db, int(job_b.id), sk1, 1)
        _make_obs(
            db,
            job_id=int(job_a.id),
            line_id=int(la.id),
            identity=id1,
            source_key=sk1,
            row_hash=_hash("hit", "a"),
            valid_from=t0,
            pod=None,
        )
        _make_obs(
            db,
            job_id=int(job_b.id),
            line_id=int(lb.id),
            identity=id1,
            source_key=sk1,
            row_hash=_hash("hit", "b"),
            valid_from=t1,
            pod=date(2026, 8, 10),
        )

        # set → set : none
        sk2 = "b132:nl:setset"
        id2 = "b132:ident:setset"
        l2a = _make_line(db, int(job_a.id), sk2, 2)
        l2b = _make_line(db, int(job_b.id), sk2, 2)
        _make_obs(
            db,
            job_id=int(job_a.id),
            line_id=int(l2a.id),
            identity=id2,
            source_key=sk2,
            row_hash=_hash("setset", "a"),
            valid_from=t0,
            pod=date(2026, 7, 1),
        )
        _make_obs(
            db,
            job_id=int(job_b.id),
            line_id=int(l2b.id),
            identity=id2,
            source_key=sk2,
            row_hash=_hash("setset", "b"),
            valid_from=t1,
            pod=date(2026, 8, 1),
        )

        # NULL → NULL : none
        sk3 = "b132:nl:nullnull"
        id3 = "b132:ident:nullnull"
        l3a = _make_line(db, int(job_a.id), sk3, 3)
        l3b = _make_line(db, int(job_b.id), sk3, 3)
        _make_obs(
            db,
            job_id=int(job_a.id),
            line_id=int(l3a.id),
            identity=id3,
            source_key=sk3,
            row_hash=_hash("nn", "a"),
            valid_from=t0,
            pod=None,
        )
        _make_obs(
            db,
            job_id=int(job_b.id),
            line_id=int(l3b.id),
            identity=id3,
            source_key=sk3,
            row_hash=_hash("nn", "b"),
            valid_from=t1,
            pod=None,
        )

        # First observation already POD'd: not a transition (no prior report)
        sk4 = "b132:nl:firstpod"
        id4 = "b132:ident:firstpod"
        l4b = _make_line(db, int(job_b.id), sk4, 4)
        _make_obs(
            db,
            job_id=int(job_b.id),
            line_id=int(l4b.id),
            identity=id4,
            source_key=sk4,
            row_hash=_hash("first", "b"),
            valid_from=t1,
            pod=date(2026, 8, 11),
        )
        db.commit()

    try:
        payload = _run(_newly(job_ids[1]))
        assert payload["count"] == 1
        row = payload["rows"][0]
        assert row["source_key"] == "b132:nl:hit"
        assert row["previous_pod"] is None
        assert row["current_pod"] == "2026-08-10"
        for key in LINE_COLUMN_KEYS:
            assert key in row
        assert row["sales_model"] == "UX3402VA"
        assert row["qty"] == 2.0
        assert row["customer"] == "GAME-SA"
        assert row["distributor"]
        assert row["date"] == "2026-08-10"
    finally:
        with SessionLocal() as db:
            for jid in job_ids:
                job = db.get(ImportJob, jid)
                if job is not None:
                    db.delete(job)
            db.commit()


def test_eta_shift_uncapped_over_public_cap_with_line_columns() -> None:
    _skip_mutations_on_shared_cip()
    t0 = datetime(2026, 8, 1, tzinfo=timezone.utc)
    t1 = t0 + timedelta(days=7)
    n = PUBLIC_ETA_SHIFT_SAMPLE_CAP + 1
    job_ids: list[int] = []
    with SessionLocal() as db:
        src = db.scalar(select(SourceDefinition).limit(1))
        if src is None:
            pytest.skip("no source_definition row")
        sid = int(src.id)
        job_a = _make_job(db, sid, "b132-eta-a.csv")
        job_b = _make_job(db, sid, "b132-eta-b.csv")
        job_ids = [int(job_a.id), int(job_b.id)]
        for i in range(n):
            sk = f"b132:eta:{i}"
            ident = f"b132:eta-ident:{i}"
            la = _make_line(db, int(job_a.id), sk, i + 1)
            lb = _make_line(db, int(job_b.id), sk, i + 1)
            _make_obs(
                db,
                job_id=int(job_a.id),
                line_id=int(la.id),
                identity=ident,
                source_key=sk,
                row_hash=_hash("eta", "a", str(i)),
                valid_from=t0,
                pod=None,
                est_pod=date(2026, 9, 1),
                promise=date(2026, 9, 1),
            )
            _make_obs(
                db,
                job_id=int(job_b.id),
                line_id=int(lb.id),
                identity=ident,
                source_key=sk,
                row_hash=_hash("eta", "b", str(i)),
                valid_from=t1,
                pod=None,
                est_pod=date(2026, 9, 11),
                promise=date(2026, 9, 1),
            )
        db.commit()

    async def _caps() -> tuple[dict, dict]:
        async with AsyncSessionLocal() as adb:
            evid, keys = identity_scope_for_job(job_ids[1])
            capped = await compute_eta_shifts(
                adb,
                evid_ids=evid,
                identity_keys=keys,
                sample_limit=50,
                require_current_incoming=False,
                cap_samples=True,
                include_line_columns=False,
            )
            uncapped = await compute_eta_shifts(
                adb,
                evid_ids=evid,
                identity_keys=keys,
                sample_limit=0,
                require_current_incoming=False,
                cap_samples=False,
                include_line_columns=True,
            )
            return capped, uncapped

    try:
        capped, uncapped = _run(_caps())
        assert capped["slipped_count"] == n
        assert len(capped["samples"]) == PUBLIC_ETA_SHIFT_SAMPLE_CAP
        assert set(capped["samples"][0].keys()) == PUBLIC_ETA_SHIFT_SAMPLE_KEYS
        assert uncapped["slipped_count"] == n
        assert len(uncapped["samples"]) == n
        for sample in uncapped["samples"]:
            for key in LINE_COLUMN_KEYS:
                assert key in sample
    finally:
        with SessionLocal() as db:
            for jid in job_ids:
                job = db.get(ImportJob, jid)
                if job is not None:
                    db.delete(job)
            db.commit()


def test_newly_landed_skips_zero_pod_prior_job() -> None:
    """A mapping-empty snapshot (all pod_date NULL) is not the prior report."""
    _skip_mutations_on_shared_cip()
    t0 = datetime(2026, 7, 21, tzinfo=timezone.utc)
    t_junk = datetime(2026, 7, 28, tzinfo=timezone.utc)
    t1 = datetime(2026, 8, 18, tzinfo=timezone.utc)
    job_ids: list[int] = []
    with SessionLocal() as db:
        src = db.scalar(select(SourceDefinition).limit(1))
        if src is None:
            pytest.skip("no source_definition row")
        sid = int(src.id)
        job_a = _make_job(db, sid, "b132-skip-a.csv")
        job_j = _make_job(db, sid, "b132-skip-junk.csv")
        job_b = _make_job(db, sid, "b132-skip-b.csv")
        job_ids = [int(job_a.id), int(job_j.id), int(job_b.id)]
        sk = "b132:nl:skip"
        ident = "b132:ident:skip"
        la = _make_line(db, int(job_a.id), sk, 1)
        lj = _make_line(db, int(job_j.id), sk, 1)
        lb = _make_line(db, int(job_b.id), sk, 1)
        _make_obs(
            db,
            job_id=int(job_a.id),
            line_id=int(la.id),
            identity=ident,
            source_key=sk,
            row_hash=_hash("skip", "a"),
            valid_from=t0,
            pod=date(2026, 7, 1),
        )
        _make_obs(
            db,
            job_id=int(job_j.id),
            line_id=int(lj.id),
            identity=ident,
            source_key=sk,
            row_hash=_hash("skip", "j"),
            valid_from=t_junk,
            pod=None,
        )
        _make_obs(
            db,
            job_id=int(job_b.id),
            line_id=int(lb.id),
            identity=ident,
            source_key=sk,
            row_hash=_hash("skip", "b"),
            valid_from=t1,
            pod=date(2026, 7, 1),
        )
        db.commit()

    try:
        payload = _run(_newly(job_ids[2]))
        assert payload["count"] == 0
        assert job_ids[1] in payload["skipped_unusable_job_ids"]
        assert job_ids[0] not in payload["skipped_unusable_job_ids"]
    finally:
        with SessionLocal() as db:
            for jid in job_ids:
                job = db.get(ImportJob, jid)
                if job is not None:
                    db.delete(job)
            db.commit()
