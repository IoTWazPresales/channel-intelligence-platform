"""Tests for full customer merge (name-similarity groups)."""

from __future__ import annotations

import os
import secrets
from datetime import date
from unittest.mock import patch

import pytest
from sqlalchemy import select

from app.core.config import get_settings
from app.db.session_sync import SessionLocal
from app.models.commercial_planner import CommercialCustomerTerm
from app.models.dimensions import DimChannel, DimCustomer, DimDistributor, DimProduct, DimRegion
from app.models.facts import FactSalesSellout
from app.services.commercial_planner.reference_bootstrap import ensure_commercial_planner_system_reference_data_sync
from app.services.customer_full_merge import (
    CustomerFullMergeError,
    confirm_customer_full_merge_sync,
    preview_customer_full_merge,
    preview_customer_full_merge_bulk,
)
from app.services.customer_full_repoint import CustomerFullRepointAbortError
from app.services.imports.dsi_customer_name_normalization import normalize_customer_name_for_similarity
from app.services.seed_demo import _seed_import_core


def _sqlalchemy_db_name(url: str) -> str:
    if not url or "://" not in url:
        return ""
    rest = url.split("://", 1)[1]
    if "/" not in rest:
        return ""
    db = rest.rsplit("/", 1)[-1]
    return db.split("?", 1)[0].strip()


def _require_disposable_or_opt_in_db() -> None:
    if os.environ.get("ALLOW_TESTS_ON_DEV_DB", "").strip() == "1":
        return
    settings = get_settings()
    if _sqlalchemy_db_name(settings.database_url) == "cip" or _sqlalchemy_db_name(settings.database_url_sync) == "cip":
        pytest.skip(
            "Refusing DB writes: set ALLOW_TESTS_ON_DEV_DB=1 or point DATABASE_URL_SYNC at a disposable database."
        )


def _seed_dims(session) -> tuple[int, int, int, int]:
    _seed_import_core(session)
    ensure_commercial_planner_system_reference_data_sync(session.connection())
    region = session.scalar(select(DimRegion).where(DimRegion.code == "NA-W"))
    if region is None:
        region = DimRegion(code="NA-W", name="North America West")
        session.add(region)
        session.flush()
    channel = session.scalar(select(DimChannel).where(DimChannel.code == "RET"))
    if channel is None:
        channel = DimChannel(code="RET", name="Retail")
        session.add(channel)
        session.flush()
    dist = session.scalar(select(DimDistributor).limit(1))
    if dist is None:
        dist = DimDistributor(code="DIST-FULL-01", name="Full Merge Dist")
        session.add(dist)
        session.flush()
    prod = session.scalar(select(DimProduct).limit(1))
    if prod is None:
        prod = DimProduct(sku="SKU-FULL-01", name="Full Merge Product", category="NB")
        session.add(prod)
        session.flush()
    session.commit()
    return int(region.id), int(channel.id), int(dist.id), int(prod.id)


def _seed_similar_pair(session, *, name_a: str, name_b: str) -> tuple[int, int, str]:
    key_a = normalize_customer_name_for_similarity(name_a)
    key_b = normalize_customer_name_for_similarity(name_b)
    assert key_a and key_a == key_b, f"names must share similarity key: {key_a!r} vs {key_b!r}"
    suffix = secrets.token_hex(4)
    c1 = DimCustomer(code=f"C-FULL-A-{suffix}", name=name_a, customer_status="active")
    c2 = DimCustomer(code=f"C-FULL-B-{suffix}", name=name_b, customer_status="unverified")
    session.add_all([c1, c2])
    session.commit()
    return int(c1.id), int(c2.id), key_a


def test_fk_discovery_in_preview() -> None:
    _require_disposable_or_opt_in_db()
    with SessionLocal() as session:
        _seed_dims(session)
        token = secrets.token_hex(4)
        c1, c2, key = _seed_similar_pair(
            session, name_a=f"Acme Retail {token}", name_b=f"Acme Retail {token} (Pty) Ltd"
        )
        preview = preview_customer_full_merge(
            session,
            similarity_key=key,
            survivor_id=c1,
            audit_note="preview enumeration",
        )
    enum = preview["fk_enumeration"]
    cols = enum["pg_constraint_fk_columns"]
    assert any("fact_sales_sellout.customer_id" in c for c in cols)
    assert any("commercial_lineup_line.customer_id" in c for c in cols)
    assert c2 in preview["loser_ids"]


def test_full_merge_repoints_facts_and_soft_redirects() -> None:
    _require_disposable_or_opt_in_db()
    with SessionLocal() as session:
        _region, _channel, dist_id, prod_id = _seed_dims(session)
        token = secrets.token_hex(4)
        c1, c2, key = _seed_similar_pair(
            session, name_a=f"Merge Test Alpha {token}", name_b=f"Merge Test Alpha {token} Ltd"
        )
        sk = f"test-full-merge-{secrets.token_hex(4)}"
        fact = FactSalesSellout(
            source_key=sk,
            product_id=prod_id,
            distributor_id=dist_id,
            customer_id=c2,
            period_start=date(2024, 3, 1),
            transaction_date=date(2024, 3, 1),
            invoice_no="INV-FM",
            units=3,
            revenue=30,
        )
        session.add(fact)
        session.commit()

        out = confirm_customer_full_merge_sync(
            session,
            similarity_key=key,
            survivor_id=c1,
            audit_note="full merge integration",
        )
        assert out["dry_run"] is False
        assert out["survivor_id"] == c1

        loser = session.get(DimCustomer, c2)
        assert loser is not None
        assert loser.merged_into_customer_id == c1
        assert loser.customer_status == "merged"

        refreshed = session.scalar(select(FactSalesSellout).where(FactSalesSellout.source_key == sk))
        assert refreshed is not None
        assert refreshed.customer_id == c1


def test_unique_per_customer_term_deduped_not_crashed() -> None:
    _require_disposable_or_opt_in_db()
    with SessionLocal() as session:
        _seed_dims(session)
        token = secrets.token_hex(4)
        c1, c2, key = _seed_similar_pair(
            session, name_a=f"Term Dedup {token}", name_b=f"Term Dedup {token} Ltd"
        )
        session.add(CommercialCustomerTerm(customer_id=c1, customer_margin_pct=0.1, customer_rebate_pct=0.02))
        session.add(CommercialCustomerTerm(customer_id=c2, customer_margin_pct=0.11, customer_rebate_pct=0.03))
        session.commit()

        confirm_customer_full_merge_sync(
            session,
            similarity_key=key,
            survivor_id=c1,
            audit_note="term dedup",
        )
        survivor_terms = list(
            session.scalars(select(CommercialCustomerTerm).where(CommercialCustomerTerm.customer_id == c1)).all()
        )
        assert len(survivor_terms) == 1
        assert not list(
            session.scalars(select(CommercialCustomerTerm).where(CommercialCustomerTerm.customer_id == c2)).all()
        )


def test_incomplete_repoint_aborts_whole_merge() -> None:
    _require_disposable_or_opt_in_db()
    with SessionLocal() as session:
        _seed_dims(session)
        token = secrets.token_hex(4)
        c1, c2, key = _seed_similar_pair(
            session, name_a=f"Abort Merge {token}", name_b=f"Abort Merge {token} Ltd"
        )

        with patch(
            "app.services.customer_full_merge.repoint_customer_footprint_full",
            side_effect=CustomerFullRepointAbortError("simulated incomplete repoint", loser_id=c2, table="fact_x"),
        ):
            with pytest.raises(CustomerFullMergeError, match="simulated"):
                confirm_customer_full_merge_sync(
                    session,
                    similarity_key=key,
                    survivor_id=c1,
                    audit_note="should abort",
                )

        loser = session.get(DimCustomer, c2)
        assert loser is not None
        assert loser.merged_into_customer_id is None
        assert loser.customer_status != "merged"


def test_bulk_preview_aggregate() -> None:
    _require_disposable_or_opt_in_db()
    with SessionLocal() as session:
        _seed_dims(session)
        token = secrets.token_hex(4)
        c1, c2, key = _seed_similar_pair(
            session,
            name_a=f"Bulk Preview {token}",
            name_b=f"Bulk Preview {token} Ltd",
        )
        bulk = preview_customer_full_merge_bulk(
            session,
            groups=[{"similarity_key": key, "survivor_id": c1}],
            audit_note="bulk preview test",
        )
    assert bulk["dry_run"] is True
    assert bulk["group_count"] == 1
    assert bulk["total_loser_customers"] == 1
    assert bulk["group_previews"]


def test_rejects_invalid_similarity_key() -> None:
    _require_disposable_or_opt_in_db()
    with SessionLocal() as session:
        with pytest.raises(CustomerFullMergeError, match="No duplicate group"):
            preview_customer_full_merge(
                session,
                similarity_key="nonexistent-key-xyz",
                survivor_id=1,
                audit_note="x",
            )


def test_products_and_distributors_not_in_merge_path() -> None:
    """Merge API only accepts dim_customer duplicate groups — not product/distributor ids."""
    _require_disposable_or_opt_in_db()
    with SessionLocal() as session:
        dist = session.scalar(select(DimDistributor).limit(1))
        prod = session.scalar(select(DimProduct).limit(1))
        assert dist is not None and prod is not None
        with pytest.raises(CustomerFullMergeError):
            preview_customer_full_merge(
                session,
                similarity_key="product-not-a-group",
                survivor_id=int(prod.id),
                audit_note="nope",
            )
        with pytest.raises(CustomerFullMergeError):
            preview_customer_full_merge(
                session,
                similarity_key="distributor-not-a-group",
                survivor_id=int(dist.id),
                audit_note="nope",
            )
