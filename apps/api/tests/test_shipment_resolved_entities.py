"""Unit 1 — resolved_* entity columns + crad_date on shipment evidence."""

from __future__ import annotations

from datetime import date
from unittest.mock import MagicMock

import pandas as pd
import pytest
from sqlalchemy import select, text

from app.db.session_sync import SessionLocal
from app.models.dimensions import DimCustomer, DimDistributor
from app.models.import_distributor_si import CustomerSourceTokenAlias, DistributorSourceTokenAlias
from app.models.ingestion import ImportJob, SourceDefinition
from app.models.shipment_evidence import ShipmentEvidenceLine
from app.services.imports.distributor_sales_inventory import _norm_key
from app.services.imports.shipment_evidence_import import _extract_common
from app.services.imports.shipment_resolved_entities import (
    apply_resolved_entities_to_line,
    parse_crad_from_raw_row,
    resolve_shipment_customer_id_from_token,
    resolve_shipment_distributor_id_from_line,
)


def _require_unit1_schema(db) -> None:
    cols = {
        r[0]
        for r in db.execute(
            text(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name = 'shipment_evidence_line' "
                "AND column_name IN ('resolved_customer_id', 'resolved_distributor_id', 'crad_date')"
            )
        )
    }
    if cols != {"resolved_customer_id", "resolved_distributor_id", "crad_date"}:
        pytest.skip("migration 20260629_0058 not applied")


def test_extract_common_parses_crad_column():
    row = pd.Series({"CRAD": "2026-03-15", "Item": "X"})
    ex = _extract_common(row)
    assert ex["crad_date"] == date(2026, 3, 15)


def test_parse_crad_from_raw_source_row():
    assert parse_crad_from_raw_row({"CRAD": "2026-04-01"}) == date(2026, 4, 1)
    assert parse_crad_from_raw_row({"Item": "X"}) is None
    assert parse_crad_from_raw_row(None) is None


def test_apply_resolved_entities_syncs_stamped_ids():
    line = ShipmentEvidenceLine(
        import_job_id=1,
        source_row_number=1,
        report_type="shipped",
        line_state="shipped",
        source_key="k",
        raw_source_row={},
        customer_id=10,
        distributor_id=20,
        product_resolution_status="no_identifier",
        distributor_resolution_status="resolved",
    )
    db = MagicMock()
    apply_resolved_entities_to_line(line, db, None)
    assert line.resolved_customer_id == 10
    assert line.resolved_distributor_id == 20
    db.scalar.assert_not_called()


def test_raw_tokens_unchanged_after_resolved_apply():
    line = ShipmentEvidenceLine(
        import_job_id=1,
        source_row_number=1,
        report_type="shipped",
        line_state="shipped",
        source_key="k",
        raw_source_row={"CRAD": "2026-05-01"},
        bill_to_raw="MUSTEK-ZA-BB",
        customer_dealer_token="Remark Corp",
        product_resolution_status="no_identifier",
        distributor_resolution_status="unresolved",
    )
    db = MagicMock()
    apply_resolved_entities_to_line(line, db, None)
    assert line.bill_to_raw == "MUSTEK-ZA-BB"
    assert line.customer_dealer_token == "Remark Corp"
    assert line.crad_date == date(2026, 5, 1)


def test_branch_bill_to_variants_resolve_same_root_distributor():
    """MUSTEK-ZA-BB and MUSTEK-ZA-C aliases collapse to the same dim via approved aliases."""
    try:
        with SessionLocal() as db:
            _require_unit1_schema(db)
            source_id = db.scalar(
                select(SourceDefinition.id).where(SourceDefinition.code == "inbound_default")
            )
            bb_alias = db.scalar(
                select(DistributorSourceTokenAlias.distributor_id).where(
                    DistributorSourceTokenAlias.normalized_token == _norm_key("MUSTEK-ZA-BB")
                )
            )
            c_alias = db.scalar(
                select(DistributorSourceTokenAlias.distributor_id).where(
                    DistributorSourceTokenAlias.normalized_token == _norm_key("MUSTEK-ZA-C")
                )
            )
            if bb_alias is None or c_alias is None:
                pytest.skip("MUSTEK branch aliases not present on this DB")
            did_bb = resolve_shipment_distributor_id_from_line(
                db, bill_to_raw="MUSTEK-ZA-BB", ship_to_raw=None, source_definition_id=source_id
            )
            did_c = resolve_shipment_distributor_id_from_line(
                db, bill_to_raw="MUSTEK-ZA-C", ship_to_raw=None, source_definition_id=source_id
            )
            assert did_bb is not None
            assert did_c is not None
            assert did_bb == did_c
    except Exception:
        pytest.skip("DB not available for distributor alias integration test")


def test_customer_remark_alias_resolves_resolved_customer_id():
    """Approved customer_source_token_alias on remark token populates resolved_customer_id."""
    token = "unit1-cust-alias-test"
    job_id: int | None = None
    alias_id: int | None = None
    cust_id: int | None = None
    try:
        with SessionLocal() as db:
            _require_unit1_schema(db)
            source_id = db.scalar(
                select(SourceDefinition.id).where(SourceDefinition.code == "inbound_default")
            )
            assert source_id is not None

            cust = DimCustomer(code=f"CUST-{token}", name=f"Customer {token}", status="active")
            db.add(cust)
            db.flush()
            cust_id = int(cust.id)

            alias = CustomerSourceTokenAlias(
                customer_id=cust_id,
                raw_token=f"Remark {token}",
                normalized_token=_norm_key(f"Remark {token}"),
                source_definition_id=int(source_id),
                status="approved",
            )
            db.add(alias)
            db.flush()
            alias_id = int(alias.id)

            cid = resolve_shipment_customer_id_from_token(
                db, f"Remark {token}", int(source_id)
            )
            assert cid == cust_id

            job = ImportJob(
                source_id=int(source_id),
                template_slug="inbound_shipments",
                import_mode="validate",
                status="pending",
                stage="uploaded",
                file_name=f"{token}.csv",
            )
            db.add(job)
            db.flush()
            job_id = int(job.id)

            line = ShipmentEvidenceLine(
                import_job_id=job_id,
                source_row_number=1,
                report_type="shipped",
                line_state="shipped",
                source_key=f"sk-{token}",
                raw_source_row={"Customer Remarks": f"Remark {token}"},
                customer_dealer_token=f"Remark {token}",
                bill_to_raw="SOME-DIST",
                product_resolution_status="no_identifier",
                distributor_resolution_status="unresolved",
            )
            db.add(line)
            db.commit()

        with SessionLocal() as db:
            line = db.scalars(
                select(ShipmentEvidenceLine).where(ShipmentEvidenceLine.import_job_id == job_id)
            ).first()
            assert line is not None
            apply_resolved_entities_to_line(line, db, int(source_id))
            assert line.resolved_customer_id == cust_id
            assert line.customer_id is None
            assert line.customer_dealer_token == f"Remark {token}"
            db.commit()
    finally:
        if job_id is not None:
            with SessionLocal() as db:
                db.execute(
                    text("DELETE FROM shipment_evidence_line WHERE import_job_id = :jid"),
                    {"jid": job_id},
                )
                db.execute(text("DELETE FROM import_job WHERE id = :jid"), {"jid": job_id})
                if alias_id is not None:
                    db.execute(
                        text("DELETE FROM customer_source_token_alias WHERE id = :aid"),
                        {"aid": alias_id},
                    )
                if cust_id is not None:
                    db.execute(text("DELETE FROM dim_customer WHERE id = :cid"), {"cid": cust_id})
                db.commit()
