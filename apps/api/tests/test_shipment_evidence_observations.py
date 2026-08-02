"""Integration tests for bitemporal shipment evidence observations (Plan D)."""

from __future__ import annotations

import os
from datetime import date, datetime, timezone

import pytest
from sqlalchemy import func, select, text

from app.db.session_sync import SessionLocal
from app.models.ingestion import ImportJob, SourceDefinition
from app.models.shipment_evidence import ShipmentEvidenceLine
from app.models.shipment_evidence_observation import ShipmentEvidenceObservation
from app.services.imports.shipment_evidence_observations import (
    append_observations_for_job_lines,
    corroboration_evidence_relation,
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
        pytest.skip("Set ALLOW_TESTS_ON_DEV_DB=1 for observation DB tests on cip")


def test_corroboration_relation_defaults_to_current_view() -> None:
    assert corroboration_evidence_relation() == "shipment_evidence_current"


def test_observation_append_idempotent() -> None:
    _skip_mutations_on_shared_cip()
    with SessionLocal() as db:
        src = db.scalar(select(SourceDefinition).limit(1))
        if src is None:
            pytest.skip("no source_definition row in configured test database")

        job = ImportJob(
            source_id=int(src.id),
            template_slug="inbound_shipments",
            status="completed",
            file_name="test_observation_append.csv",
            created_at=datetime.now(timezone.utc),
            completed_at=datetime.now(timezone.utc),
        )
        db.add(job)
        db.flush()

        line = ShipmentEvidenceLine(
            import_job_id=int(job.id),
            source_key="test:order:OU|PO|1|SKU",
            source_row_number=2,
            report_type="xxomrpt0027_order",
            line_state="open_order",
            raw_source_row={"order_no": "PO"},
            product_resolution_status="no_match",
            distributor_resolution_status="unresolved",
            order_no="PO",
            order_line="1",
            item_code="SKU",
            operating_unit="OU",
            promise_date=date(2026, 1, 15),
        )
        db.add(line)
        db.flush()

        n1 = append_observations_for_job_lines(db, job, [line])
        n2 = append_observations_for_job_lines(db, job, [line])
        db.commit()

        assert n1 == 1
        assert n2 == 1
        count = db.scalar(
            select(func.count()).select_from(ShipmentEvidenceObservation).where(
                ShipmentEvidenceObservation.import_job_id == int(job.id)
            )
        )
        assert int(count or 0) == 1


def test_current_view_exists_after_migration() -> None:
    _skip_mutations_on_shared_cip()
    with SessionLocal() as db:
        row = db.execute(
            text(
                """
                SELECT 1 FROM information_schema.views
                WHERE table_schema = 'public' AND table_name = 'shipment_evidence_current'
                """
            )
        ).first()
        if row is None:
            pytest.skip("Migration 20260623_0050 not applied on this database")
        assert row[0] == 1
