"""Tests for shipment re-validate orphan line purge (BACKLOG-007)."""

from __future__ import annotations

import os
from datetime import datetime, timezone

import pytest
from sqlalchemy import select, text

from app.db.session_sync import SessionLocal
from app.models.ingestion import ImportJob, SourceDefinition
from app.models.shipment_evidence import ShipmentEvidenceLine
from app.services.imports.shipment_evidence_import import _purge_orphan_shipment_evidence_lines


def _skip_mutations_on_shared_cip() -> None:
    if os.environ.get("ALLOW_TESTS_ON_DEV_DB", "").strip() == "1":
        return
    pytest.skip("Set ALLOW_TESTS_ON_DEV_DB=1 for shipment orphan purge DB test")


def test_purge_orphan_shipment_evidence_lines() -> None:
    _skip_mutations_on_shared_cip()
    with SessionLocal() as db:
        assert db.scalar(text("SELECT current_database()")) == "cip"
        src = db.scalar(select(SourceDefinition).limit(1))
        if src is None:
            pytest.skip("no source_definition")

        job = ImportJob(
            source_id=int(src.id),
            template_slug="inbound_shipments",
            status="completed",
            created_at=datetime.now(timezone.utc),
        )
        db.add(job)
        db.flush()

        keep = ShipmentEvidenceLine(
            import_job_id=int(job.id),
            source_key="keep:key",
            source_row_number=1,
            report_type="xxomrpt0027_order",
            line_state="open_order",
            raw_source_row={},
            product_resolution_status="no_match",
            distributor_resolution_status="unresolved",
        )
        orphan = ShipmentEvidenceLine(
            import_job_id=int(job.id),
            source_key="orphan:key",
            source_row_number=2,
            report_type="xxomrpt0027_order",
            line_state="open_order",
            raw_source_row={},
            product_resolution_status="no_match",
            distributor_resolution_status="unresolved",
        )
        db.add_all([keep, orphan])
        db.flush()

        removed = _purge_orphan_shipment_evidence_lines(db, int(job.id), {"keep:key"})
        db.commit()

        assert removed == 1
        remaining = db.scalars(
            select(ShipmentEvidenceLine.source_key).where(ShipmentEvidenceLine.import_job_id == int(job.id))
        ).all()
        assert list(remaining) == ["keep:key"]
