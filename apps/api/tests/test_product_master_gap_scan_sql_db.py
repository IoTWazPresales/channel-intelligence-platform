"""Catalogue-gap scan: SQL DISTINCT token collection equals the old per-row Python loop.

Real PostgreSQL on cip_test, synthetic records only, one rolled-back transaction per test. The old
implementation is kept below as a private copy and compared with the new one on the same data
(seeded rows plus whatever cip_test already holds). Seeded tokens start with ``!`` so they sort
ahead of real catalogue tokens and fall inside a small ``limit``.
"""

from __future__ import annotations

import sys
import uuid
from datetime import UTC, date, datetime
from typing import Any
from unittest.mock import patch

import pytest
from app.db.session_sync import SessionLocal
from app.models.cpor import CporCase, CporClaimEvidenceLine
from app.models.dimensions import DimCustomer
from app.models.iam import Tenant
from app.models.import_distributor_si import ImportEntityMappingCandidate
from app.models.ingestion import ImportJob, ImportTemplate, SourceDefinition
from app.models.shipment_evidence import ShipmentEvidenceLine
from app.services.imports import product_master_gap_resolve as gap
from app.services.imports.cst_mapping_candidates import CST_PRODUCT_ENTITY
from app.services.imports.distributor_sales_inventory import (
    ProductResolutionIndex,
    _product_token_key,
)
from app.services.imports.shipment_evidence_rows import load_evidence_rows
from sqlalchemy import select, text
from tests.shipment_evidence_fixtures import add_evidence_line, reobserve

_UNRESOLVED = ("no_match", "inactive_only", "ambiguous", "no_identifier")
NBSP = chr(0x00A0)
EM_SPACE = chr(0x2003)
IDEOGRAPHIC_SPACE = chr(0x3000)


# --- the implementation before the SQL rewrite (trunk 4d2ff66a), same meaning ------------------


def _old_collect_tokens(session) -> set[str]:
    tokens: set[str] = set()
    rows = load_evidence_rows(
        session,
        where=(
            ShipmentEvidenceLine.product_id.is_(None),
            ShipmentEvidenceLine.product_resolution_status.in_(_UNRESOLVED),
        ),
        order_by_id=False,
    )
    for line in rows:
        payload = (
            (
                line.item_code,
                line.ean_code,
                line.upc_code,
                line.sales_model_name,
                line.customer_item,
                line.mpor_item_no,
            )
            if line.has_payload
            else ()
        )
        for field in (line.product_resolution_token, *payload):
            t = gap._norm_token(field)
            if t:
                tokens.add(t)
                break
    for c in session.scalars(
        select(ImportEntityMappingCandidate).where(
            ImportEntityMappingCandidate.entity_type == "product_identifier",
            ImportEntityMappingCandidate.status == "needs_review",
        )
    ).all():
        t = gap._norm_token(getattr(c, "normalized_key", None))
        if t:
            tokens.add(t)
    for c in session.scalars(
        select(ImportEntityMappingCandidate).where(
            ImportEntityMappingCandidate.entity_type == CST_PRODUCT_ENTITY,
            ImportEntityMappingCandidate.status.in_(("needs_review", "ignored")),
        )
    ).all():
        t = gap._norm_token(getattr(c, "normalized_key", None))
        if t:
            tokens.add(t)
    for r in session.scalars(
        select(CporClaimEvidenceLine).where(CporClaimEvidenceLine.product_id.is_(None))
    ).all():
        t = gap._norm_token(r.source_model_token)
        if t:
            tokens.add(t)
    return tokens


def _old_scan(session, *, limit: int = 500) -> dict[str, Any]:
    tokens = _old_collect_tokens(session)
    token_list = sorted(tokens)[:limit]
    preview = gap.preview_gap_resolve(session, token_list)
    matched = [i for i in preview["items"] if i.get("matched")]
    return {
        "scanned_tokens": len(token_list),
        "matched": matched,
        "matched_count": len(matched),
        "truncated": len(tokens) > limit,
    }


# --- fixtures ----------------------------------------------------------------------------------


@pytest.fixture
def db():
    session = SessionLocal()
    try:
        assert session.execute(text("SELECT current_database()")).scalar() == "cip_test"
        if session.get(Tenant, "default") is None:
            session.add(Tenant(id="default", name="Default"))
            session.flush()
        yield session
    finally:
        session.rollback()
        session.close()


def _job(db, tag: str) -> ImportJob:
    template = ImportTemplate(
        slug=f"gs-{tag}", display_name="gap scan", pipeline_handler="inbound_shipments"
    )
    db.add(template)
    db.flush()
    source = SourceDefinition(
        import_template_id=int(template.id), code=f"gs-{tag}", name="gap scan", source_kind="file"
    )
    db.add(source)
    db.flush()
    job = ImportJob(
        tenant_id="default",
        source_id=int(source.id),
        template_slug="inbound_shipments",
        status="completed",
        stage="loaded",
        file_name="gap-scan-fixture.xlsx",
        completed_at=datetime(2026, 11, 1, tzinfo=UTC),
    )
    db.add(job)
    db.flush()
    return job


def _seed(db) -> dict[str, Any]:
    """Synthetic open gaps in every source; returns the tokens the scan must (not) find."""
    tag = uuid.uuid4().hex[:10]
    p = f"!gs-{tag}"
    job = _job(db, tag)
    n = 0

    def line(*, observe: bool = True, status: str = "no_match", **fields):
        nonlocal n
        n += 1
        return add_evidence_line(
            db,
            observe=observe,
            import_job_id=int(job.id),
            source_sheet="S",
            source_row_number=n,
            source_key=f"gs:{tag}:{n}",
            product_resolution_status=status,
            raw_source_row={},
            quantity=1,
            **fields,
        )

    # Resolution token set (padded, lower case): it wins over the payload item code.
    line(product_resolution_token=f"  {p}-tok1 ", item_code=f"{p}-item-shadowed")
    # Duplicate of tok1 after normalization, on another line.
    line(product_resolution_token=f"{p}-TOK1", ean_code=f"{p}-ean-shadowed")
    # No token; the first payload fields normalize to empty (NBSP + tab, and ""): UPC counts.
    line(item_code=f"{NBSP} \t", ean_code="", upc_code=f"{p}-upc2")
    # Same UPC in other casing: one normalized token.
    line(item_code=IDEOGRAPHIC_SPACE, upc_code=f"{p}-UPC2")
    # Inner whitespace collapses; the later customer_item is shadowed.
    line(sales_model_name=f"{p}-model   x", customer_item=f"{p}-cust-shadowed")
    line(customer_item=f"{p}-model x")
    line(mpor_item_no=f"{p}-mpor7")
    # No observation at all: only the line's token counts.
    line(observe=False, product_resolution_token=f"{p}-tok3")
    line(observe=False)
    # Whitespace-only token and an empty payload: contributes nothing.
    line(product_resolution_token=f" {EM_SPACE} ")
    # Two observations: only the newest payload counts.
    moved = line(item_code=f"{p}-old-item")
    reobserve(db, moved, item_code=f"{p}-new-item")
    # Not open: a resolved status is excluded even with tokens.
    line(
        status="resolved",
        product_resolution_token=f"{p}-resolved-tok",
        item_code=f"{p}-resolved-item",
    )

    def cand(entity_type: str, key: str, status: str) -> None:
        db.add(
            ImportEntityMappingCandidate(
                import_job_id=int(job.id),
                entity_type=entity_type,
                normalized_key=key,
                status=status,
                row_count=2,
            )
        )

    cand("product_identifier", f"{p}-cand1 ", "needs_review")
    # The scan reads needs_review only for product_identifier candidates.
    cand("product_identifier", f"{p}-cand-ignored", "ignored")
    cand("product_identifier", f"{p}-tok1", "needs_review")  # overlaps a shipment token
    cand(CST_PRODUCT_ENTITY, f"{p}-cst1", "needs_review")
    cand(CST_PRODUCT_ENTITY, f"{p}-cst2", "ignored")
    cand(CST_PRODUCT_ENTITY, f"{p}-cst-resolved", "resolved")
    db.flush()

    customer = DimCustomer(tenant_id="default", code=f"GS-{tag}", name="Gap scan fixture customer")
    db.add(customer)
    db.flush()
    claim_case = CporCase(
        tenant_id="default",
        case_code=f"GS-{tag}",
        customer_id=int(customer.id),
        promotion_type="Fixture promo",
        window_start=date(2026, 1, 1),
        window_end=date(2026, 1, 31),
    )
    db.add(claim_case)
    db.flush()
    for i, token in enumerate((f"{p}-cpor1", f" {p}-CPOR1", None, "\t")):
        db.add(
            CporClaimEvidenceLine(
                case_id=int(claim_case.id),
                import_job_id=int(job.id),
                source_model_token=token,
                sale_date=date(2026, 1, 2),
                units=1,
                source_key=f"gs:{tag}:claim:{i}",
            )
        )
    db.flush()

    up = p.upper()
    expected = {
        f"{up}-{s}"
        for s in (
            "TOK1", "UPC2", "MODEL X", "MPOR7", "TOK3",
            "NEW-ITEM", "CAND1", "CST1", "CST2", "CPOR1",
        )
    }
    absent = {
        f"{up}-{s}"
        for s in (
            "ITEM-SHADOWED", "EAN-SHADOWED", "CUST-SHADOWED", "OLD-ITEM", "RESOLVED-TOK",
            "RESOLVED-ITEM", "CAND-IGNORED", "CST-RESOLVED",
        )
    }
    return {"prefix": up, "expected": expected, "absent": absent}


def _index_matching(tokens: list[str]) -> ProductResolutionIndex:
    return ProductResolutionIndex(
        sku_to_id={},
        part_number_to_ids={},
        sales_model_name_to_ids={},
        model_name_to_ids={},
        marketing_name_to_ids={},
        ean_to_ids={},
        upc_to_ids={},
        alias_value_to_ids={_product_token_key(t): (900_000 + i,) for i, t in enumerate(tokens)},
        steward_alias_by_key={},
        products_by_id={},
    )


# --- tests -------------------------------------------------------------------------------------


def test_sql_whitespace_class_is_exactly_python_isspace():
    python_ws = {chr(c) for c in range(sys.maxunicode + 1) if chr(c).isspace()}
    assert set(gap._PY_WHITESPACE) == python_ws
    assert len(gap._PY_WHITESPACE) == len(python_ws)


def test_token_set_matches_old_loop_on_seeded_and_existing_data(db):
    seeded = _seed(db)
    new_tokens = gap._collect_open_gap_tokens(db)
    old_tokens = _old_collect_tokens(db)
    assert new_tokens == old_tokens
    ours = {t for t in new_tokens if t.startswith(seeded["prefix"])}
    assert ours == seeded["expected"]
    assert not (seeded["absent"] & new_tokens)


def test_scan_result_identical_to_old_with_truncation(db):
    seeded = _seed(db)
    ordered = sorted(seeded["expected"])
    # Match every other seeded token so the matched list has gaps; its order must survive.
    index = _index_matching(ordered[::2])
    # Small window: preview_gap_resolve reloads every open shipment line once per token.
    limit = 3
    with patch.object(gap, "get_product_resolution_index", return_value=index):
        new = gap.scan_open_gaps_for_matches(db, limit=limit)
        old = _old_scan(db, limit=limit)
    assert new == old
    assert new["truncated"] is True
    assert new["scanned_tokens"] == limit
    # Seeded tokens sort first, so the scanned window is ours and the matched tokens are known.
    assert [m["token"] for m in new["matched"]] == ordered[:limit:2]
    assert new["matched_count"] == len(new["matched"]) > 0
