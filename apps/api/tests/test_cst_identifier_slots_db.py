"""N-0111 (Warren 2026-10-19): sell-through product identifiers are separate slots, resolved in the
platform order Part number -> Barcode -> Sales model (customer product code through the customer's
aliases). One rolled-back transaction; cip_test only.

- a file whose part number, barcode and sales model all agree;
- a file with only the EAN; only the UPC (matches Product Master UPC); only the sales model;
- identifiers that disagree are flagged and not loaded as a guess; the steward sees every identifier;
- the customer's own product code resolves only through that customer's aliases;
- totals-only pricing: unit price and cost are derived, marked, and the totals stay as given;
- a file read through an older layout (one product column) loads exactly as before;
- a saved older layout can be re-mapped into the new slots.
"""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine, func, select, text
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.sync_url import sqlalchemy_sync_engine_url
from app.models.customer_article_alias import CustomerArticleAlias
from app.models.customer_report_config import CustomerReportConfig
from app.models.customer_sellthrough_layout import CustomerSellthroughLayout
from app.models.dimensions import DimCustomer, DimProduct
from app.models.fact_customer_sellthrough import FactCustomerSellthrough
from app.models.import_customer_sellthrough_staging import ImportCustomerSellthroughStagingLine
from app.models.import_distributor_si import ImportEntityMappingCandidate
from app.models.ingestion import ImportJob
from app.services.imports.cst_layouts import (
    create_customer_upload_jobs,
    find_matching_layout,
    inspect_files_for_customer,
)
from app.services.imports.cst_mapping_candidates import resolve_cst_candidate_sync
from app.services.imports.customer_sell_through import resolve_product_id_for_sellthrough
from app.services.imports.distributor_sales_inventory import _load_product_resolution_index
from app.services.imports.product_resolution_index_cache import invalidate_product_resolution_index_cache


@pytest.fixture
def session():
    engine = create_engine(sqlalchemy_sync_engine_url(get_settings().database_url_sync))
    with engine.connect() as conn:
        if conn.execute(text("select current_database()")).scalar() != "cip_test":
            pytest.skip("cip_test only")
        if not conn.execute(
            text(
                "select count(*) from information_schema.columns where table_name = "
                "'import_customer_sellthrough_staging_line' and column_name = 'product_match_tier'"
            )
        ).scalar():
            pytest.skip("20261019_0044 is not applied")
        conn.rollback()
        outer = conn.begin()
        db = Session(bind=conn, join_transaction_mode="create_savepoint")
        invalidate_product_resolution_index_cache()
        try:
            yield db
        finally:
            db.close()
            outer.rollback()
            invalidate_product_resolution_index_cache()
    engine.dispose()


def _customer(db: Session, code: str) -> int:
    cust = DimCustomer(code=code, name=f"{code} name", is_key_account=True)
    db.add(cust)
    db.flush()
    db.add(CustomerReportConfig(customer_id=cust.id, reports_expected=True, expected_cadence="weekly"))
    db.flush()
    return int(cust.id)


def _product(db: Session, tag: str, n: int) -> DimProduct:
    p = DimProduct(
        sku=f"N0111M-SKU-{tag}",
        name=f"N0111M product {tag}",
        part_number=f"N0111M-PN-{tag}",
        ean=f"99900011100{n}1",
        upc=f"99900011100{n}2"[1:],
        sales_model_name=f"N0111M-MODEL-{tag}",
    )
    db.add(p)
    db.flush()
    invalidate_product_resolution_index_cache()
    return p


def _two_products(db: Session) -> tuple[DimProduct, DimProduct]:
    return _product(db, "A", 1), _product(db, "B", 2)


def _csv(header: list[str], rows: list[list]) -> bytes:
    return ("\n".join(",".join("" if c is None else str(c) for c in r) for r in [header, *rows]) + "\n").encode()


# Headers no alias knows, so the mapping step has to map them; the layout names each identifier.
HEADER = ["PN", "Strekkode", "Modelnaam", "Stuks", "Voorraad", "Verkoopdatum"]
SLOTS = {
    "PN": "raw_part_number_token",
    "Strekkode": "raw_barcode_token",
    "Modelnaam": "raw_sales_model_token",
    "Stuks": "units_sold",
    "Voorraad": "reported_soh",
    "Verkoopdatum": "raw_period_ref",
}
DAY = "2026-03-02"


def _upload(db: Session, cid: int, data: bytes, mapping: dict[str, str], *, name: str = "Layout") -> dict:
    info = inspect_files_for_customer(db, cid, [("file.csv", data)])[0]
    out = create_customer_upload_jobs(
        db,
        customer_id=cid,
        filenames_and_bytes=[("file.csv", data)],
        new_layouts=[{"signature": info["layout_signature"], "name": name, "field_mapping": mapping}],
        import_mode="apply",
    )
    assert [o["outcome"] for o in out] == ["created"], out
    return out[0]


def _lines(db: Session, job_id: int) -> list[ImportCustomerSellthroughStagingLine]:
    return list(
        db.scalars(
            select(ImportCustomerSellthroughStagingLine)
            .where(ImportCustomerSellthroughStagingLine.import_job_id == job_id)
            .order_by(ImportCustomerSellthroughStagingLine.source_row_number)
        ).all()
    )


def _fact_products(db: Session, cid: int) -> list[int]:
    return sorted(
        int(p) for p in db.scalars(select(FactCustomerSellthrough.product_id).where(FactCustomerSellthrough.customer_id == cid))
    )


def test_a_file_with_all_three_identifiers_agreeing_loads_on_the_part_number_tier(session: Session) -> None:
    a, b = _two_products(session)
    cid = _customer(session, "N0111M-AGREE")
    data = _csv(
        HEADER,
        [
            [a.part_number, a.ean, a.sales_model_name, 3, 20, DAY],
            [b.part_number, b.ean, b.sales_model_name, 5, 30, DAY],
        ],
    )
    out = _upload(session, cid, data, SLOTS)
    lines = _lines(session, out["import_job_id"])
    assert [ln.resolved_product_id for ln in lines] == [a.id, b.id]
    assert {ln.product_match_tier for ln in lines} == {"part_number"}
    first = lines[0]
    # Each identifier is stored separately, as the file gave it.
    assert (first.raw_part_number_token, first.raw_barcode_token, first.raw_sales_model_token) == (
        a.part_number,
        a.ean,
        a.sales_model_name,
    )
    assert first.raw_product_token is None
    check = first.product_identifier_check
    assert check["result"] == "resolved" and check["product_id"] == a.id
    assert [(o["slot"], o["status"]) for o in check["outcomes"]] == [
        ("part_number", "unique"),
        ("barcode", "unique"),
        ("sales_model", "unique"),
    ]
    assert _fact_products(session, cid) == sorted([a.id, b.id])


@pytest.mark.parametrize(
    "column, header, value, tier",
    [
        ("raw_barcode_token", "Strekkode", lambda p: p.ean, "ean"),
        ("raw_barcode_token", "Strekkode", lambda p: p.upc, "upc"),
        ("raw_sales_model_token", "Modelnaam", lambda p: p.sales_model_name, "sales_model_name"),
        ("raw_part_number_token", "PN", lambda p: p.part_number, "part_number"),
    ],
    ids=["only-EAN", "only-UPC-matches-PM-UPC", "only-sales-model", "only-part-number"],
)
def test_a_file_with_one_identifier_resolves_on_that_identifiers_tier(session: Session, column, header, value, tier) -> None:
    a, b = _two_products(session)
    cid = _customer(session, f"N0111M-ONE-{tier.upper()}")
    mapping = {header: column, "Stuks": "units_sold", "Voorraad": "reported_soh", "Verkoopdatum": "raw_period_ref"}
    data = _csv([header, "Stuks", "Voorraad", "Verkoopdatum"], [[value(a), 4, 10, DAY], [value(b), 6, 12, DAY]])
    out = _upload(session, cid, data, mapping)
    lines = _lines(session, out["import_job_id"])
    assert [ln.resolved_product_id for ln in lines] == [a.id, b.id]
    assert {ln.product_match_tier for ln in lines} == {tier}
    assert getattr(lines[0], column) == value(a)
    assert _fact_products(session, cid) == sorted([a.id, b.id])
    assert float(session.scalar(select(func.sum(FactCustomerSellthrough.units_sold)).where(FactCustomerSellthrough.customer_id == cid))) == 10.0


def test_identifiers_that_disagree_are_flagged_and_not_loaded_as_a_guess(session: Session) -> None:
    a, b = _two_products(session)
    cid = _customer(session, "N0111M-DISAGREE")
    data = _csv(
        HEADER,
        [
            [a.part_number, a.ean, a.sales_model_name, 3, 20, DAY],  # agrees
            [a.part_number, b.ean, None, 7, 9, DAY],  # part number says A, barcode says B
            ["N0111M-UNKNOWN", b.upc, None, 2, 4, DAY],  # unknown part number, barcode finds B
        ],
    )
    out = _upload(session, cid, data, SLOTS)
    job_id = out["import_job_id"]
    ok, bad, by_barcode = _lines(session, job_id)
    assert (ok.resolved_product_id, ok.product_match_tier) == (a.id, "part_number")
    # The disagreeing row is not resolved to either product and says why.
    assert bad.resolved_product_id is None and bad.resolution_status == "unresolved"
    assert bad.product_match_tier == "identifier_conflict"
    assert bad.product_identifier_check["result"] == "conflict"
    assert {tuple(o["product_ids"]) for o in bad.product_identifier_check["outcomes"]} == {(a.id,), (b.id,)}
    # An unmatched identifier is not a disagreement: the barcode decides.
    assert (by_barcode.resolved_product_id, by_barcode.product_match_tier) == (b.id, "upc")
    # Only the two agreeing rows loaded; the disagreeing row is nowhere in the facts.
    assert _fact_products(session, cid) == sorted([a.id, b.id])
    assert float(session.scalar(select(func.sum(FactCustomerSellthrough.units_sold)).where(FactCustomerSellthrough.customer_id == cid))) == 5.0

    # The steward's candidate shows every identifier the row carried, and the conflict.
    cand = session.scalar(
        select(ImportEntityMappingCandidate).where(
            ImportEntityMappingCandidate.import_job_id == job_id,
            ImportEntityMappingCandidate.entity_type == "cst_product_token",
        )
    )
    assert cand is not None and cand.normalized_key == a.part_number.lower() and cand.row_count == 1
    assert cand.context["identifier_conflict_rows"] == 1
    shown = cand.context["identifier_rows"][0]
    assert shown["identifiers"] == {"part_number": a.part_number, "barcode": b.ean}
    assert shown["tier"] == "identifier_conflict"
    assert {m["slot"] for m in shown["matched"]} == {"part_number", "barcode"}

    # The steward chooses A; reprocessing the job then loads the row.
    from app.ingestion.pipeline import process_import_job_sync

    resolve_cst_candidate_sync(session, job_id, int(cand.id), int(a.id))
    process_import_job_sync(session, job_id)
    lines = _lines(session, job_id)
    assert [ln.resolved_product_id for ln in lines] == [a.id, a.id, b.id]
    assert lines[1].product_match_tier == "steward"
    assert float(session.scalar(select(func.sum(FactCustomerSellthrough.units_sold)).where(FactCustomerSellthrough.customer_id == cid))) == 12.0


def test_the_customers_own_product_code_resolves_only_through_the_customers_aliases(session: Session) -> None:
    a, b = _two_products(session)
    cid = _customer(session, "N0111M-CODE")
    other = _customer(session, "N0111M-CODE-OTHER")
    session.add(CustomerArticleAlias(customer_id=cid, article_no_normalized="art-77", product_id=a.id, status="confirmed"))
    # Another customer's alias for the same code must not be used.
    session.add(CustomerArticleAlias(customer_id=other, article_no_normalized="art-88", product_id=b.id, status="confirmed"))
    session.flush()
    header = ["Kliente Kode", "Stuks", "Voorraad", "Verkoopdatum"]
    mapping = {"Kliente Kode": "raw_article_token", "Stuks": "units_sold", "Voorraad": "reported_soh", "Verkoopdatum": "raw_period_ref"}
    data = _csv(
        header,
        [
            ["ART-77", 3, 20, DAY],  # this customer's alias -> A
            ["ART-88", 1, 5, DAY],  # only another customer has this alias
            [b.sku, 2, 5, DAY],  # equals a Product Master SKU, but a customer code is not matched to Product Master
        ],
    )
    out = _upload(session, cid, data, mapping)
    lines = _lines(session, out["import_job_id"])
    assert [ln.resolved_product_id for ln in lines] == [a.id, None, None]
    assert lines[0].product_match_tier == "customer_alias"
    assert _fact_products(session, cid) == [a.id]


def test_a_customer_code_alias_that_disagrees_with_the_barcode_is_a_conflict(session: Session) -> None:
    a, b = _two_products(session)
    cid = _customer(session, "N0111M-CODE-CONFLICT")
    session.add(CustomerArticleAlias(customer_id=cid, article_no_normalized="art-77", product_id=a.id, status="confirmed"))
    session.flush()
    header = ["Strekkode", "Kliente Kode", "Stuks", "Voorraad", "Verkoopdatum"]
    mapping = {
        "Strekkode": "raw_barcode_token",
        "Kliente Kode": "raw_article_token",
        "Stuks": "units_sold",
        "Voorraad": "reported_soh",
        "Verkoopdatum": "raw_period_ref",
    }
    data = _csv(header, [[b.ean, "ART-77", 3, 20, DAY], [a.ean, "ART-77", 2, 20, DAY]])
    out = _upload(session, cid, data, mapping)
    bad, good = _lines(session, out["import_job_id"])
    assert bad.product_match_tier == "identifier_conflict" and bad.resolved_product_id is None
    assert (good.resolved_product_id, good.product_match_tier) == (a.id, "ean")


def test_totals_only_pricing_derives_the_unit_figures_and_marks_them(session: Session) -> None:
    a, b = _two_products(session)
    cid = _customer(session, "N0111M-TOTALS")
    header = ["PN", "Stuks", "Voorraad", "Verkoopdatum", "Omset", "Koste"]
    mapping = {
        "PN": "raw_part_number_token",
        "Stuks": "units_sold",
        "Voorraad": "reported_soh",
        "Verkoopdatum": "raw_period_ref",
        "Omset": "total_sell_amount",
        "Koste": "total_cost_amount",
    }
    data = _csv(header, [[a.part_number, 4, 10, DAY, 400, 300], [b.part_number, 0, 10, DAY, 50, 30]])
    out = _upload(session, cid, data, mapping)
    la, lb = _lines(session, out["import_job_id"])
    assert (float(la.unit_sell_price), float(la.unit_cost)) == (100.0, 75.0)
    derived = la.raw_row_payload["_cst_derived"]
    assert derived["unit_sell_price_from_total"] and derived["unit_cost_from_total"]
    # Totals stay as the file gave them.
    assert derived["total_sell_amount"] == 400.0 and derived["total_cost_amount"] == 300.0
    assert la.raw_row_payload["Omset"] == "400" and la.raw_row_payload["Koste"] == "300"
    # Zero units: nothing is derived.
    assert lb.unit_sell_price is None and lb.unit_cost is None
    fact_a = session.scalar(
        select(FactCustomerSellthrough).where(FactCustomerSellthrough.customer_id == cid, FactCustomerSellthrough.product_id == a.id)
    )
    assert (float(fact_a.unit_sell_price), float(fact_a.unit_cost)) == (100.0, 75.0)
    assert fact_a.raw_source_row["_cst_derived"]["unit_sell_price_from_total"] is True


def test_a_file_read_through_an_older_layout_loads_exactly_as_before(session: Session) -> None:
    a, b = _two_products(session)
    cid = _customer(session, "N0111M-OLD")
    header = ["Artikel Nr", "Stuks", "Voorraad", "Verkoopdatum", "Sales Model Name"]
    old_mapping = {
        "Artikel Nr": "raw_product_token",
        "Stuks": "units_sold",
        "Voorraad": "reported_soh",
        "Verkoopdatum": "raw_period_ref",
    }
    data = _csv(
        header,
        [
            [a.ean, 3, 20, DAY, None],  # barcode in the old single column
            [b.sku, 5, 30, DAY, None],  # item code in the old single column
            ["N0111M-NOPE", 1, 9, DAY, a.sales_model_name],  # found through an unmapped payload column, as before
            ["N0111M-NOPE-2", 1, 9, DAY, None],  # nothing matches
        ],
    )
    out = _upload(session, cid, data, old_mapping)
    lines = _lines(session, out["import_job_id"])
    idx = _load_product_resolution_index(session)
    # The same answer the former resolver gives, row by row.
    expected = [
        resolve_product_id_for_sellthrough(
            idx,
            ln.raw_product_token,
            session=session,
            customer_id=cid,
            article_token=ln.raw_article_token,
            raw_row_payload=ln.raw_row_payload,
            as_of=ln.period_start_date,
        )
        for ln in lines
    ]
    assert expected == [a.id, b.id, a.id, None]
    assert [ln.resolved_product_id for ln in lines] == expected
    assert [ln.product_match_tier for ln in lines] == ["any_identifier", "any_identifier", "any_identifier", None]
    # The new slots stay empty and no per-identifier check is made for an older layout.
    for ln in lines:
        assert ln.raw_part_number_token is None and ln.raw_barcode_token is None and ln.raw_sales_model_token is None
        assert ln.product_identifier_check is None
    assert _fact_products(session, cid) == sorted([a.id, b.id])  # rows 1 and 3 are one product and week
    layout = find_matching_layout(session, cid, header)
    assert layout.field_mapping == old_mapping  # not rewritten


def test_an_older_layout_is_offered_a_re_map_and_keeps_loading_until_it_is_re_mapped(session: Session) -> None:
    a, b = _two_products(session)
    cid = _customer(session, "N0111M-REMAP")
    header = ["Artikel Nr", "Stuks", "Voorraad", "Verkoopdatum"]
    old_mapping = {"Artikel Nr": "raw_product_token", "Stuks": "units_sold", "Voorraad": "reported_soh", "Verkoopdatum": "raw_period_ref"}
    first = _csv(header, [[a.ean, 3, 20, DAY]])
    _upload(session, cid, first, old_mapping, name="Weekly")
    layout = find_matching_layout(session, cid, header)

    info = inspect_files_for_customer(session, cid, [("next.csv", _csv(header, [[b.ean, 1, 5, "2026-03-09"]]))])[0]
    assert info["layout"]["id"] == layout.id and info["layout"]["legacy_product_slot"] is True
    assert info["layout"]["mapping"] == old_mapping

    # Uploading again without a re-map still works through the older column.
    nxt = _csv(header, [[b.ean, 1, 5, "2026-03-09"]])
    out = create_customer_upload_jobs(session, customer_id=cid, filenames_and_bytes=[("next.csv", nxt)], import_mode="apply")
    assert [o["outcome"] for o in out] == ["created"]
    assert [ln.product_match_tier for ln in _lines(session, out[0]["import_job_id"])] == ["any_identifier"]

    # Re-map the old column to the barcode slot: the layout is updated in place, not duplicated.
    new_mapping = {**old_mapping, "Artikel Nr": "raw_barcode_token"}
    out = create_customer_upload_jobs(
        session,
        customer_id=cid,
        filenames_and_bytes=[("again.csv", _csv(header, [[b.ean, 2, 5, "2026-03-16"]]))],
        new_layouts=[{"signature": info["layout_signature"], "layout_id": layout.id, "name": "Weekly", "field_mapping": new_mapping}],
        import_mode="apply",
    )
    assert [o["outcome"] for o in out] == ["created"]
    session.refresh(layout)
    assert layout.field_mapping == new_mapping
    assert session.scalar(select(func.count(CustomerSellthroughLayout.id)).where(CustomerSellthroughLayout.customer_id == cid)) == 1
    (line,) = _lines(session, out[0]["import_job_id"])
    assert (line.resolved_product_id, line.product_match_tier, line.raw_barcode_token) == (b.id, "ean", b.ean)
    info2 = inspect_files_for_customer(session, cid, [("x.csv", first)])[0]
    assert info2["layout"]["legacy_product_slot"] is False


def test_a_re_map_without_an_identifier_is_refused_and_leaves_the_layout_alone(session: Session) -> None:
    a, _b = _two_products(session)
    cid = _customer(session, "N0111M-REMAP-BAD")
    header = ["Artikel Nr", "Stuks", "Voorraad", "Verkoopdatum"]
    old_mapping = {"Artikel Nr": "raw_product_token", "Stuks": "units_sold", "Voorraad": "reported_soh", "Verkoopdatum": "raw_period_ref"}
    data = _csv(header, [[a.ean, 3, 20, DAY]])
    _upload(session, cid, data, old_mapping)
    layout = find_matching_layout(session, cid, header)
    sig = inspect_files_for_customer(session, cid, [("a.csv", data)])[0]["layout_signature"]
    out = create_customer_upload_jobs(
        session,
        customer_id=cid,
        filenames_and_bytes=[("a.csv", data)],
        new_layouts=[{"signature": sig, "layout_id": layout.id, "name": "x", "field_mapping": {"Stuks": "units_sold"}}],
        import_mode="apply",
    )
    assert out[0]["outcome"] == "error" and "product identifier" in out[0]["error"]
    session.refresh(layout)
    assert layout.field_mapping == old_mapping


def test_a_job_row_that_is_unresolved_is_counted_in_the_candidate_with_all_its_identifiers(session: Session) -> None:
    """No match anywhere: the candidate is keyed by the first identifier in the platform order and lists the rest."""
    _two_products(session)
    cid = _customer(session, "N0111M-NOMATCH")
    data = _csv(HEADER, [["N0111M-X1", "5550001110001", "N0111M-MODEL-X", 3, 20, DAY], ["N0111M-X1", "5550001110001", None, 2, 5, "2026-03-09"]])
    out = _upload(session, cid, data, SLOTS)
    cand = session.scalar(
        select(ImportEntityMappingCandidate).where(
            ImportEntityMappingCandidate.import_job_id == out["import_job_id"],
            ImportEntityMappingCandidate.entity_type == "cst_product_token",
        )
    )
    assert cand.normalized_key == "n0111m-x1" and cand.row_count == 2
    assert cand.context["identifier_rows"][0]["identifiers"] == {
        "part_number": "N0111M-X1",
        "barcode": "5550001110001",
        "sales_model": "N0111M-MODEL-X",
    }
    assert "identifier_conflict_rows" not in cand.context
    job = session.get(ImportJob, out["import_job_id"])
    assert job.staged_metadata["customer_sellthrough_flat"]["unresolved"] == 2
