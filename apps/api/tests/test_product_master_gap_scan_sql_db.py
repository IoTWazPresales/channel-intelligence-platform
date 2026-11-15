"""Catalogue-gap scan: SQL DISTINCT token collection and once-per-source preview equal the old code.

Real PostgreSQL on cip_test, synthetic records only, one rolled-back transaction per test. The old
implementation (token collection, per-token preview, apply on top of it) is kept below as a
private copy and compared with the new one on the same data
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
from app.models.dimensions import DimCustomer, DimProduct
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


# --- preview / apply before the per-source rewrite (b2aa6998), same meaning --------------------
# ``load_once`` only hoists the read-only shipment load out of the token loop (the session is not
# changed inside a preview, so every per-token load returns the same rows); the per-token matching
# is verbatim. Default False is the old code exactly.


def _old_count_shipment(session, tok: str, rows=None) -> tuple[int, set[int]]:
    jobs: set[int] = set()
    n = 0
    lines = gap._unresolved_shipment_rows(session) if rows is None else rows
    for line in lines:
        if gap._line_token_match(line, tok):
            n += 1
            if line.import_job_id is not None:
                jobs.add(int(line.import_job_id))
    return n, jobs


def _old_count_dsi_staging(session, tok: str) -> tuple[int, set[int]]:
    cands = session.scalars(
        select(ImportEntityMappingCandidate).where(
            ImportEntityMappingCandidate.entity_type == "product_identifier",
            ImportEntityMappingCandidate.status.in_(("needs_review", "ignored")),
        )
    ).all()
    jobs: set[int] = set()
    n = 0
    for c in cands:
        if gap._norm_token(getattr(c, "normalized_key", None)) == tok:
            n += 1
            if c.import_job_id is not None:
                jobs.add(int(c.import_job_id))
    return n, jobs


def _old_count_cpor_claims(session, tok: str) -> tuple[int, set[int]]:
    rows = session.scalars(
        select(CporClaimEvidenceLine).where(CporClaimEvidenceLine.product_id.is_(None))
    ).all()
    jobs: set[int] = set()
    n = 0
    for r in rows:
        if gap._norm_token(r.source_model_token) == tok:
            n += 1
            if r.import_job_id is not None:
                jobs.add(int(r.import_job_id))
    return n, jobs


def _old_count_cst_staging(session, tok: str) -> tuple[int, set[int]]:
    cands = session.scalars(
        select(ImportEntityMappingCandidate).where(
            ImportEntityMappingCandidate.entity_type == CST_PRODUCT_ENTITY,
            ImportEntityMappingCandidate.status.in_(("needs_review", "ignored")),
        )
    ).all()
    jobs: set[int] = set()
    n = 0
    for c in cands:
        if gap._norm_token(getattr(c, "normalized_key", None)) == tok:
            n += int(c.row_count or 1)
            if c.import_job_id is not None:
                jobs.add(int(c.import_job_id))
    return n, jobs


def _old_preview(session, tokens: list[str], *, load_once: bool = False) -> dict[str, Any]:
    ship_rows = gap._unresolved_shipment_rows(session) if load_once and tokens else None
    items: list[dict[str, Any]] = []
    for raw in tokens:
        m = gap.match_token_to_product(session, raw)
        tok = m.get("token") or gap._norm_token(raw)
        ship_n, ship_jobs = _old_count_shipment(session, tok, ship_rows)
        dsi_n, dsi_jobs = _old_count_dsi_staging(session, tok)
        claim_n, claim_jobs = _old_count_cpor_claims(session, tok)
        cst_n, cst_jobs = _old_count_cst_staging(session, tok)
        flags: list[str] = []
        flag_detail: str | None = None
        if dsi_n > 0:
            flags.append("dsi_facts_repoint_deferred")
            flag_detail = (
                "DSI fact source_key includes product_id — staging-only repoint this unit; "
                "leftovers remain FLAG not BLOCK"
            )
        items.append(
            {
                **m,
                "counts": {
                    "shipment": ship_n,
                    "dsi_staging": dsi_n,
                    "cpor_claim": claim_n,
                    "cst_staging": cst_n,
                    "dsi_facts": 0,
                },
                "flags": flags,
                "flag_detail": flag_detail,
                "affected_job_ids": sorted(ship_jobs | dsi_jobs | claim_jobs | cst_jobs),
            }
        )
    return {
        "items": items,
        "matched_count": sum(1 for i in items if i.get("matched")),
        "unmatched_count": sum(1 for i in items if not i.get("matched")),
        "data_unavailable": False,
    }


def _old_apply(session, *, tokens: list[str], confirm: bool, write_alias: bool = True, actor=None):
    if not confirm:
        return {"ok": False, "error": "confirm_required", "applied": False}

    preview = _old_preview(session, tokens)
    applied: list[dict[str, Any]] = []
    total = len(preview["items"])

    for item in preview["items"]:
        if not item.get("matched"):
            applied.append({**item, "action": "skipped_unmatched"})
            continue
        pid = int(item["product_id"])
        tok = str(item["token"])
        ship_u = gap._repoint_shipment(session, tok, pid)
        dsi_u = gap._repoint_dsi_staging(session, tok, pid)
        claim_u = gap._repoint_cpor_claims(session, tok, pid)
        cst_u = gap._repoint_cst_staging(session, tok, pid)
        alias_written = False
        alias_skipped_conflict = False
        if write_alias and (ship_u or dsi_u or claim_u or cst_u):
            alias_written, alias_skipped_conflict = gap._ensure_product_alias(session, tok, pid)
        applied.append(
            {
                "token": tok,
                "product_id": pid,
                "match_tier": item.get("match_tier"),
                "action": "repointed",
                "updated": {
                    "shipment_lines": ship_u,
                    "dsi_staging_candidates": dsi_u,
                    "cpor_claim_lines": claim_u,
                    "cst_staging_candidates": cst_u,
                    "dsi_facts": 0,
                },
                "flags": item.get("flags") or [],
                "flag_detail": item.get("flag_detail"),
                "alias_written": alias_written,
                "alias_skipped_conflict": alias_skipped_conflict,
                "actor": actor,
            }
        )

    session.flush()
    gap.invalidate_product_resolution_index_cache()
    return {
        "ok": True,
        "applied": True,
        "items": applied,
        "summary": {
            "tokens": total,
            "repointed": sum(1 for a in applied if a.get("action") == "repointed"),
            "skipped": sum(1 for a in applied if a.get("action") != "repointed"),
        },
    }


def _old_scan(session, *, limit: int = 500) -> dict[str, Any]:
    tokens = _old_collect_tokens(session)
    token_list = sorted(tokens)[:limit]
    preview = _old_preview(session, token_list)
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
    return {"prefix": up, "expected": expected, "absent": absent, "tag": tag, "job_id": int(job.id)}


def _index_matching(tokens: list[str], ids: list[int] | None = None) -> ProductResolutionIndex:
    if ids is None:
        ids = [900_000 + i for i in range(len(tokens))]
    return ProductResolutionIndex(
        sku_to_id={},
        part_number_to_ids={},
        sales_model_name_to_ids={},
        model_name_to_ids={},
        marketing_name_to_ids={},
        ean_to_ids={},
        upc_to_ids={},
        alias_value_to_ids={
            _product_token_key(t): (pid,) for t, pid in zip(tokens, ids, strict=True)
        },
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
    # Small window: the old preview reloads every open shipment line once per token.
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


def _seed_preview_extras(db, seeded: dict[str, Any]) -> None:
    """Grouping cases on top of ``_seed``: identical lines, 2nd job, multi-field hit, CST 0 rows."""
    tag, p = seeded["tag"], seeded["prefix"]
    job2 = _job(db, f"{tag}-2")
    n = 0

    def line(job_id: int, **fields) -> None:
        nonlocal n
        n += 1
        add_evidence_line(
            db,
            import_job_id=job_id,
            source_sheet="S",
            source_row_number=1000 + n,
            source_key=f"gs:{tag}:x{n}",
            product_resolution_status="ambiguous",
            raw_source_row={"r": n},
            quantity=1,
            **fields,
        )

    # Two identical lines in one job (one SQL group of 2) and one more in another job.
    line(seeded["job_id"], product_resolution_token=f"{p}-GRP")
    line(seeded["job_id"], product_resolution_token=f"{p}-GRP")
    line(int(job2.id), item_code=f"{p.lower()}-grp ")
    # The same key in two fields of one line counts the line once.
    line(seeded["job_id"], product_resolution_token=f"{p}-MULTI", ean_code=f" {p}-multi")
    for job_id, key, count in ((int(job2.id), f"{p}-cst1", 3), (int(job2.id), f"{p}-cst0", 0)):
        db.add(
            ImportEntityMappingCandidate(
                import_job_id=job_id,
                entity_type=CST_PRODUCT_ENTITY,
                normalized_key=key,
                status="needs_review",
                row_count=count,
            )
        )
    db.flush()


def _by_token(preview: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {i["token"]: i for i in preview["items"]}


def test_preview_identical_to_old_on_seeded_and_existing_tokens(db):
    seeded = _seed(db)
    _seed_preview_extras(db, seeded)
    p = seeded["prefix"]
    suffixes = (
        "TOK1", "ITEM-SHADOWED", "EAN-SHADOWED", "CUST-SHADOWED", "UPC2", "MODEL X", "MPOR7",
        "TOK3", "OLD-ITEM", "NEW-ITEM", "RESOLVED-TOK", "RESOLVED-ITEM", "CAND1", "CAND-IGNORED",
        "CST1", "CST2", "CST-RESOLVED", "CPOR1", "GRP", "MULTI", "CST0", "NOWHERE",
    )
    seeded_tokens = [f"{p}-{s}" for s in suffixes]
    real = sorted(t for t in gap._collect_open_gap_tokens(db) if not t.startswith("!GS-"))
    existing = real[:2] + real[-2:]
    tokens = [
        *seeded_tokens,
        f"  {p.lower()}-tok1 ",  # padded, lower case
        f"{p}-TOK1",  # duplicate
        f"{p.lower()}-model   x",  # inner whitespace
        "",
        " ",
        EM_SPACE,
        *existing,
    ]
    index = _index_matching(seeded_tokens[::2] + existing[:1])
    with patch.object(gap, "get_product_resolution_index", return_value=index):
        # The new preview never loads open shipment lines row by row.
        with patch.object(gap, "_unresolved_shipment_rows", side_effect=AssertionError("row load")):
            new = gap.preview_gap_resolve(db, tokens)
        old = _old_preview(db, tokens, load_once=True)
    assert new == old
    assert len(new["items"]) == len(tokens)
    assert 0 < new["matched_count"] < len(tokens)

    by = _by_token(new)
    job = seeded["job_id"]
    grp = by[f"{p}-GRP"]
    assert grp["counts"]["shipment"] == 3
    assert job in grp["affected_job_ids"] and len(grp["affected_job_ids"]) == 2
    assert by[f"{p}-MULTI"]["counts"]["shipment"] == 1
    assert by[f"{p}-TOK1"]["counts"]["shipment"] == 2
    assert by[f"{p}-TOK1"]["counts"]["dsi_staging"] == 1
    # Preview counts a line when ANY field matches, so shadowed payload values still count.
    assert by[f"{p}-ITEM-SHADOWED"]["counts"]["shipment"] == 1
    assert by[f"{p}-OLD-ITEM"]["counts"]["shipment"] == 0
    assert by[f"{p}-CAND-IGNORED"]["counts"]["dsi_staging"] == 1
    assert by[f"{p}-CST1"]["counts"]["cst_staging"] == 2 + 3
    assert by[f"{p}-CST0"]["counts"]["cst_staging"] == 1
    assert by[f"{p}-CPOR1"]["counts"]["cpor_claim"] == 2
    assert by[f"{p}-NOWHERE"]["counts"] == {
        "shipment": 0, "dsi_staging": 0, "cpor_claim": 0, "cst_staging": 0, "dsi_facts": 0,
    }


def test_preview_empty_token_list(db):
    assert gap.preview_gap_resolve(db, []) == _old_preview(db, [])


def _apply_snapshot(db, job_id: int) -> dict[str, Any]:
    db.flush()
    return {
        "lines": db.execute(
            select(
                ShipmentEvidenceLine.id,
                ShipmentEvidenceLine.product_id,
                ShipmentEvidenceLine.product_resolution_status,
                ShipmentEvidenceLine.product_resolution_detail,
            )
            .where(ShipmentEvidenceLine.import_job_id == job_id)
            .order_by(ShipmentEvidenceLine.id)
        ).all(),
        "candidates": db.execute(
            select(
                ImportEntityMappingCandidate.id,
                ImportEntityMappingCandidate.status,
                ImportEntityMappingCandidate.suggested_entity_id,
                ImportEntityMappingCandidate.match_reason,
                ImportEntityMappingCandidate.context,
            )
            .where(ImportEntityMappingCandidate.import_job_id == job_id)
            .order_by(ImportEntityMappingCandidate.id)
        ).all(),
        "claims": db.execute(
            select(CporClaimEvidenceLine.id, CporClaimEvidenceLine.product_id)
            .where(CporClaimEvidenceLine.import_job_id == job_id)
            .order_by(CporClaimEvidenceLine.id)
        ).all(),
    }


def test_apply_identical_to_old_in_savepoints(db):
    seeded = _seed(db)
    p, tag, job = seeded["prefix"], seeded["tag"], seeded["job_id"]
    products = [
        DimProduct(tenant_id="default", sku=f"GS-{tag}-P{i}", name="Gap scan fixture product")
        for i in (1, 2)
    ]
    db.add_all(products)
    db.flush()
    p1, p2 = (int(x.id) for x in products)
    tokens = [f"{p}-TOK1", f"  {p.lower()}-tok1 ", f"{p}-CPOR1", f"{p}-CST1", f"{p}-NOWHERE"]
    index = _index_matching([f"{p}-TOK1", f"{p}-CPOR1", f"{p}-CST1"], [p1, p2, p2])
    before = _apply_snapshot(db, job)

    def run(fn) -> tuple[dict[str, Any], dict[str, Any]]:
        savepoint = db.begin_nested()
        try:
            out = fn(db, tokens=tokens, confirm=True, write_alias=False, actor="parity")
            return out, _apply_snapshot(db, job)
        finally:
            savepoint.rollback()
            db.expire_all()

    with patch.object(gap, "get_product_resolution_index", return_value=index):
        new_out, new_state = run(gap.apply_gap_resolve)
        assert _apply_snapshot(db, job) == before
        old_out, old_state = run(_old_apply)
        assert _apply_snapshot(db, job) == before
    assert new_out == old_out
    assert new_state == old_state
    assert new_state != before
    assert new_out["summary"] == {"tokens": 5, "repointed": 4, "skipped": 1}
    first = new_out["items"][0]
    assert first["updated"]["shipment_lines"] == 2
    assert first["updated"]["dsi_staging_candidates"] == 1
