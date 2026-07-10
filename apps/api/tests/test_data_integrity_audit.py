"""Data integrity audit — unit + DB-seeded violation detection."""

from __future__ import annotations

import secrets
from datetime import date

import pytest
from sqlalchemy import text

from app.db.session_sync import SessionLocal
from app.models.commercial_lineup import CommercialLineupCase, CommercialLineupCasePo, CommercialLineupLine
from app.models.dimensions import DimCustomer, DimProduct
from app.models.facts import FactInboundShipment
from app.models.ingestion import ImportJob, SourceDefinition
from app.models.purchase_order import PurchaseOrder
from app.models.shipment_evidence import ShipmentEvidenceLine
from app.services.data_integrity_audit import (
    _evidence_invoice_key,
    _link_still_derives_confidence,
    collect_evidence_fact_parity,
    collect_evidence_true_dupes,
    run_data_integrity_audit_sync,
)


def test_evidence_invoice_split_not_true_dupe():
    """Legitimate invoice-line splits must not share the same 5b key."""
    k1 = _evidence_invoice_key(
        delivery_no="D1", item_code="ITEM", purchase_order_id=10, invoice_line="1"
    )
    k2 = _evidence_invoice_key(
        delivery_no="D1", item_code="ITEM", purchase_order_id=10, invoice_line="2"
    )
    assert k1 != k2


def test_link_drift_detects_no_product_on_case():
    case = CommercialLineupCase(
        id=1,
        inferred_period_start=date(2026, 1, 1),
        import_intent="t",
        source_context="t",
    )
    ship = FactInboundShipment(
        id=1,
        purchase_order_id=99,
        product_id=500,
        line_state="shipped",
        source_key="sk",
        report_type="shipped",
        raw_source_row={},
        product_resolution_status="ok",
        distributor_resolution_status="ok",
        crad_date=date(2026, 2, 1),
    )
    lineup_line = CommercialLineupLine(
        id=1,
        case_id=1,
        product_id=100,
        customer_id=1,
        quantity_units=10,
        row_status="imported",
    )
    failures = _link_still_derives_confidence(
        case=case,
        shipments=[ship],
        lineup_by_product={100: [lineup_line]},
        redirect_map={1: 1},
    )
    assert "no_product_on_case" in failures


def _require_audit_schema(db) -> None:
    needed = {
        "commercial_lineup_case",
        "commercial_lineup_case_po",
        "commercial_lineup_line",
        "fact_inbound_shipment",
        "shipment_evidence_line",
        "purchase_order",
    }
    for table in needed:
        if db.scalar(text("SELECT to_regclass(:t)"), {"t": f"public.{table}"}) is None:
            pytest.skip(f"{table} not migrated")


def _token() -> str:
    return secrets.token_hex(6)


@pytest.mark.integration
def test_audit_seeded_violations_on_db():
    """Seed one violation per check where schema allows; assert detection."""
    tok = _token()
    job_id: int | None = None
    po_ids: list[int] = []
    case_ids: list[int] = []
    cust_ids: list[int] = []
    product_ids: list[int] = []
    fact_ids: list[int] = []
    evidence_ids: list[int] = []

    try:
        with SessionLocal() as db:
            _require_audit_schema(db)
            source_id = db.scalar(
                text("SELECT id FROM source_definition WHERE code = 'inbound_default' LIMIT 1")
            )
            if not source_id:
                pytest.skip("inbound_default source missing")

            job = ImportJob(
                source_id=int(source_id),
                template_slug="inbound_shipments",
                import_mode="validate",
                status="completed",
                stage="loaded",
                file_name=f"audit_{tok}.csv",
            )
            db.add(job)
            db.flush()
            job_id = int(job.id)

            c1 = DimCustomer(code=f"AUD-C1-{tok}", name=f"Audit C1 {tok}", customer_status="active")
            c2 = DimCustomer(code=f"AUD-C2-{tok}", name=f"Audit C2 {tok}", customer_status="active")
            db.add_all([c1, c2])
            db.flush()
            cust_ids.extend([int(c1.id), int(c2.id)])

            prod_match = DimProduct(
                sku=f"AUD-P-M-{tok}",
                name=f"Audit match {tok}",
                product_line="NB",
                business_unit="NB",
            )
            prod_other = DimProduct(
                sku=f"AUD-P-O-{tok}",
                name=f"Audit other {tok}",
                product_line="NB",
                business_unit="NB",
            )
            db.add_all([prod_match, prod_other])
            db.flush()
            product_ids.extend([int(prod_match.id), int(prod_other.id)])

            po_a = PurchaseOrder(po_number_raw=f"AUD-PO-A-{tok}", po_number_norm=f"AUDPOA{tok}")
            po_b = PurchaseOrder(po_number_raw=f"AUD-PO-B-{tok}", po_number_norm=f"AUDPOB{tok}")
            po_cross = PurchaseOrder(po_number_raw=f"AUD-PO-X-{tok}", po_number_norm=f"AUDPOX{tok}")
            db.add_all([po_a, po_b, po_cross])
            db.flush()
            po_ids.extend([int(po_a.id), int(po_b.id), int(po_cross.id)])

            case_ok = CommercialLineupCase(
                file_name=f"ok_{tok}.xlsx",
                period_label="2026 Q1",
                inferred_period_start=date(2026, 1, 1),
                business_unit="NB",
                product_line="NB",
                commercial_status="draft_imported",
                import_intent="audit",
                source_context="audit",
            )
            case_sup = CommercialLineupCase(
                file_name=f"sup_{tok}.xlsx",
                period_label="2026 Q1",
                inferred_period_start=date(2026, 1, 1),
                business_unit="NB",
                product_line="NB",
                commercial_status="superseded",
                superseded_by_case_id=None,
                import_intent="audit",
                source_context="audit",
            )
            case_q1 = CommercialLineupCase(
                file_name=f"q1_{tok}.xlsx",
                period_label="2026 Q1",
                inferred_period_start=date(2026, 1, 1),
                business_unit="NB",
                product_line="NB",
                commercial_status="draft_imported",
                import_intent="audit",
                source_context="audit",
            )
            case_q2 = CommercialLineupCase(
                file_name=f"q2_{tok}.xlsx",
                period_label="2026 Q2",
                inferred_period_start=date(2026, 4, 1),
                business_unit="NB",
                product_line="NB",
                commercial_status="draft_imported",
                import_intent="audit",
                source_context="audit",
            )
            db.add_all([case_ok, case_sup, case_q1, case_q2])
            db.flush()
            case_ids.extend([int(case_ok.id), int(case_sup.id), int(case_q1.id), int(case_q2.id)])
            case_sup.superseded_by_case_id = int(case_ok.id)

            db.add(
                CommercialLineupLine(
                    case_id=int(case_ok.id),
                    product_id=int(prod_match.id),
                    customer_id=int(c1.id),
                    quantity_units=100,
                    row_status="imported",
                )
            )

            # link_drift: linked PO but shipment product not on case
            db.add(CommercialLineupCasePo(case_id=int(case_ok.id), purchase_order_id=int(po_a.id)))
            # superseded_link
            db.add(CommercialLineupCasePo(case_id=int(case_sup.id), purchase_order_id=int(po_b.id)))
            # cross_quarter_po
            db.add(CommercialLineupCasePo(case_id=int(case_q1.id), purchase_order_id=int(po_cross.id)))
            db.add(CommercialLineupCasePo(case_id=int(case_q2.id), purchase_order_id=int(po_cross.id)))

            fact_key = f"ship:AUD-DEL-{tok}|AUD-ITEM-{tok}|{int(po_a.id)}"
            fact = FactInboundShipment(
                import_job_id=job_id,
                source_key=f"audit-fact-{tok}",
                fact_upsert_key=fact_key,
                line_state="shipped",
                report_type="shipped",
                raw_source_row={},
                product_resolution_status="ok",
                distributor_resolution_status="ok",
                purchase_order_id=int(po_a.id),
                product_id=int(prod_match.id),
                resolved_customer_id=int(c2.id),
                delivery_no=f"AUD-DEL-{tok}",
                item_code=f"AUD-ITEM-{tok}",
                quantity=30,
                crad_date=date(2026, 2, 10),
            )
            db.add(fact)
            db.flush()
            fact_ids.append(int(fact.id))

            # customer_mismatch link on po_a (c2 shipment vs c1 lineup)
            # evidence: true dupe (5b) — same invoice line twice
            for _ in range(2):
                ev = ShipmentEvidenceLine(
                    import_job_id=job_id,
                    source_row_number=1,
                    report_type="acza_workbook_shipped",
                    line_state="shipped",
                    source_key=f"audit-ev-dup-{tok}-{_}",
                    raw_source_row={},
                    product_resolution_status="ok",
                    distributor_resolution_status="ok",
                    delivery_no=f"AUD-ED-{tok}",
                    item_code=f"AUD-EI-{tok}",
                    purchase_order_id=int(po_b.id),
                    invoice_line="1",
                    quantity=5,
                )
                db.add(ev)
                db.flush()
                evidence_ids.append(int(ev.id))

            # evidence_fact_parity (6): multi-line group sums 30; fact holds 10 only
            parity_key = f"ship:AUD-PAR-{tok}|AUD-PARI-{tok}|{int(po_b.id)}"
            db.add(
                FactInboundShipment(
                    import_job_id=job_id,
                    source_key=f"audit-parity-fact-{tok}",
                    fact_upsert_key=parity_key,
                    line_state="shipped",
                    report_type="shipped",
                    raw_source_row={},
                    product_resolution_status="ok",
                    distributor_resolution_status="ok",
                    purchase_order_id=int(po_b.id),
                    delivery_no=f"AUD-PAR-{tok}",
                    item_code=f"AUD-PARI-{tok}",
                        quantity=15,
                )
            )
            for inv in ("1", "2"):
                ev = ShipmentEvidenceLine(
                    import_job_id=job_id,
                    source_row_number=2,
                    report_type="acza_workbook_shipped",
                    line_state="shipped",
                    source_key=f"audit-parity-ev-{tok}-{inv}",
                    raw_source_row={},
                    product_resolution_status="ok",
                    distributor_resolution_status="ok",
                    delivery_no=f"AUD-PAR-{tok}",
                    item_code=f"AUD-PARI-{tok}",
                    purchase_order_id=int(po_b.id),
                    invoice_line=inv,
                    quantity=15,
                )
                db.add(ev)
                db.flush()
                evidence_ids.append(int(ev.id))

            db.commit()

        with SessionLocal() as db:
            report = run_data_integrity_audit_sync(db, sample_limit=50)
            by_name = {c.check: c for c in report.checks}

            drift = [s for s in by_name["link_drift"].samples if s.get("purchase_order_id") == po_ids[0]]
            assert by_name["link_drift"].count >= 1
            assert drift and "customer_mismatch" in drift[0]["failed_predicates"]

            sup = [s for s in by_name["superseded_link"].samples if s.get("case_id") == case_ids[1]]
            assert by_name["superseded_link"].count >= 1
            assert sup

            cross = [s for s in by_name["cross_quarter_po"].samples if s.get("purchase_order_id") == po_ids[2]]
            assert by_name["cross_quarter_po"].count >= 1
            assert cross

            mismatch = [s for s in by_name["customer_mismatch"].samples if s.get("purchase_order_id") == po_ids[0]]
            assert by_name["customer_mismatch"].count >= 1
            assert mismatch

            from unittest.mock import patch

            _read_off = "app.services.imports.shipment_evidence_read.shipment_bitemporal_read_enabled"
            with patch(_read_off, return_value=False):
                true_dupes = [
                    s for s in collect_evidence_true_dupes(db) if s.get("delivery_no") == f"AUD-ED-{tok}"
                ]
            assert true_dupes
            assert true_dupes[0].get("violation") == "corpus_duplicate_shipped_invoice_line"
            assert true_dupes[0].get("duplicate_row_count") == 2

            with patch(_read_off, return_value=False):
                parity = [
                    s
                    for s in collect_evidence_fact_parity(db)
                    if s.get("fact_upsert_key") == f"ship:AUD-PAR-{tok}|AUD-PARI-{tok}|{po_ids[1]}"
                ]
            assert parity and parity[0].get("issue") == "single_line_undercount"

            with patch(_read_off, return_value=False):
                split_hits = [
                    s
                    for s in collect_evidence_true_dupes(db)
                    if s.get("delivery_no") == f"AUD-PAR-{tok}"
                ]
            assert not split_hits

            # fact_key constraint meta always present
            assert "fact_upsert_key_unique_constraint" in by_name["fact_key_dupes"].meta

    finally:
        with SessionLocal() as db:
            db.execute(
                text(
                    "DELETE FROM shipment_evidence_line WHERE source_key LIKE :pat OR delivery_no LIKE :dtok"
                ),
                {"pat": f"audit-%{tok}%", "dtok": f"AUD-%-{tok}"},
            )
            db.execute(
                text(
                    "DELETE FROM fact_inbound_shipment WHERE source_key LIKE :pat OR fact_upsert_key LIKE :dtok"
                ),
                {"pat": f"audit-%{tok}%", "dtok": f"%{tok}%"},
            )
            db.execute(
                text(
                    """
                    DELETE FROM commercial_lineup_case_po
                    WHERE purchase_order_id IN (
                        SELECT id FROM purchase_order WHERE po_number_raw LIKE :pat
                    )
                    """
                ),
                {"pat": f"AUD-PO-%-{tok}"},
            )
            db.execute(
                text("DELETE FROM commercial_lineup_line WHERE case_id IN (SELECT id FROM commercial_lineup_case WHERE file_name LIKE :pat)"),
                {"pat": f"%_{tok}.xlsx"},
            )
            db.execute(
                text("DELETE FROM commercial_lineup_case WHERE file_name LIKE :pat OR import_intent = 'audit'"),
                {"pat": f"%_{tok}.xlsx"},
            )
            db.execute(text("DELETE FROM purchase_order WHERE po_number_raw LIKE :pat"), {"pat": f"AUD-PO-%-{tok}"})
            db.execute(text("DELETE FROM dim_product WHERE sku LIKE :pat"), {"pat": f"AUD-P-%-{tok}"})
            db.execute(text("DELETE FROM dim_customer WHERE code LIKE :pat"), {"pat": f"AUD-C%-{tok}"})
            db.execute(text("DELETE FROM import_job WHERE file_name = :fn"), {"fn": f"audit_{tok}.csv"})
            db.commit()


def test_lineup_duplicate_ingestion_detects_identical_fingerprints():
    from app.services.data_integrity_audit import check_lineup_duplicate_ingestion

    with SessionLocal() as db:
        db_name = db.scalar(text("SELECT current_database()"))
        if db_name == "cip":
            pytest.skip("seeded duplicate-ingestion test must not write to cip")

        prod = DimProduct(sku="dup-ing-sku", name="dup", part_number="dup", is_active=True)
        db.add(prod)
        db.flush()
        ps = date(2026, 1, 1)
        c1 = CommercialLineupCase(
            file_name="dup_lineup.xlsx",
            period_label="2026 Q1",
            inferred_period_start=ps,
            business_unit="NB",
            commercial_status="draft_imported",
            import_intent="audit",
            source_context="audit",
            notes="sheet=NB; audit",
        )
        c2 = CommercialLineupCase(
            file_name="dup_lineup.xlsx",
            period_label="2026 Q1",
            inferred_period_start=ps,
            business_unit="NV",
            commercial_status="draft_imported",
            import_intent="audit",
            source_context="audit",
            notes="sheet=NR; audit",
        )
        db.add_all([c1, c2])
        db.flush()
        for case_id, bu in ((c1.id, "NB"), (c2.id, "NV")):
            _ = bu
            db.add(
                CommercialLineupLine(
                    case_id=int(case_id),
                    source_row_number=1,
                    product_id=int(prod.id),
                    customer_id=1,
                    quantity_units=10,
                    row_status="imported",
                )
            )
        db.commit()

        try:
            result = check_lineup_duplicate_ingestion(db, sample_limit=10)
            hits = [s for s in result.samples if s.get("file_name") == "dup_lineup.xlsx"]
            assert result.count >= 1
            assert hits
            assert sorted(hits[0]["case_ids"]) == sorted([int(c1.id), int(c2.id)])
        finally:
            db.execute(
                text("DELETE FROM commercial_lineup_line WHERE case_id IN (:a, :b)"),
                {"a": int(c1.id), "b": int(c2.id)},
            )
            db.execute(
                text("DELETE FROM commercial_lineup_case WHERE id IN (:a, :b)"),
                {"a": int(c1.id), "b": int(c2.id)},
            )
            db.execute(text("DELETE FROM dim_product WHERE sku = 'dup-ing-sku'"))
            db.commit()
