"""Tests for customer alias-scope merge workflow."""

from __future__ import annotations

import os
import secrets
from datetime import date
from unittest.mock import patch

import pytest
from sqlalchemy import inspect, select

from app.core.config import get_settings
from app.db.session_sync import SessionLocal
from app.models.dimensions import DimChannel, DimCustomer, DimDistributor, DimProduct, DimRegion
from app.models.facts import FactSalesSellout
from app.services.commercial_planner.reference_bootstrap import ensure_commercial_planner_system_reference_data_sync
from app.services.customer_alias_scope_merge import (
    confirm_customer_alias_scope_merge_sync,
    preview_customer_alias_scope_merge,
)
from app.services.imports.provisional_entity_consolidation import repoint_customer_id_references_full
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
    assert dist is not None
    prod = session.scalar(select(DimProduct).limit(1))
    assert prod is not None
    return int(region.id), int(channel.id), int(dist.id), int(prod.id)


def _seed_two_customers(session) -> tuple[int, int]:
    suffix = secrets.token_hex(4)
    c1 = DimCustomer(code=f"C-ALIAS-A-{suffix}", name="Alias Customer A", customer_status="active")
    c2 = DimCustomer(code=f"C-ALIAS-B-{suffix}", name="Alias Customer B", customer_status="unverified")
    session.add_all([c1, c2])
    session.commit()
    return int(c1.id), int(c2.id)


def test_merge_preview_fk_breakdown() -> None:
    _require_disposable_or_opt_in_db()
    with SessionLocal() as session:
        _seed_dims(session)
        c1, c2 = _seed_two_customers(session)
        token = f"acme dealer {secrets.token_hex(4)}"
        with patch(
            "app.services.customer_alias_scope_merge._load_scope_conflict_customer_ids",
            return_value=[c1, c2],
        ):
            preview = preview_customer_alias_scope_merge(
                session,
                normalized_token=token,
                source_definition_id=None,
                distributor_id=None,
                survivor_id=c1,
                audit_note="test preview",
            )
        assert preview["dry_run"] is True
        assert preview["survivor_id"] == c1
        assert c2 in preview["loser_ids"]
        assert preview["loser_plans"]


def test_merge_confirm_honors_survivor_and_soft_redirect() -> None:
    _require_disposable_or_opt_in_db()
    with SessionLocal() as session:
        _region, _channel, dist_id, prod_id = _seed_dims(session)
        c1, c2 = _seed_two_customers(session)
        token = f"acme dealer {secrets.token_hex(4)}"
        sk = f"test-sellout-alias-merge-{secrets.token_hex(4)}"
        fact = FactSalesSellout(
            source_key=sk,
            product_id=prod_id,
            distributor_id=dist_id,
            customer_id=c2,
            period_start=date(2024, 1, 1),
            transaction_date=date(2024, 1, 15),
            invoice_no="INV-1",
            units=1,
            revenue=10,
        )
        session.add(fact)
        session.commit()

        with patch(
            "app.services.customer_alias_scope_merge._load_scope_conflict_customer_ids",
            return_value=[c1, c2],
        ), patch(
            "app.services.customer_alias_scope_merge._repoint_aliases_in_scope",
            return_value=0,
        ):
            out = confirm_customer_alias_scope_merge_sync(
                session,
                normalized_token=token,
                source_definition_id=None,
                distributor_id=None,
                survivor_id=c1,
                audit_note="steward merge test",
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


def test_repoint_customer_id_references_full_covers_specs() -> None:
    _require_disposable_or_opt_in_db()
    with SessionLocal() as session:
        _region, _channel, dist_id, prod_id = _seed_dims(session)
        c1, c2 = _seed_two_customers(session)
        sk = f"test-repoint-alias-{secrets.token_hex(4)}"
        fact = FactSalesSellout(
            source_key=sk,
            product_id=prod_id,
            distributor_id=dist_id,
            customer_id=c2,
            period_start=date(2024, 2, 1),
            transaction_date=date(2024, 2, 1),
            invoice_no="INV-2",
            units=2,
            revenue=20,
        )
        session.add(fact)
        session.commit()
        repoint_customer_id_references_full(session, loser_id=c2, keeper_id=c1)
        session.commit()
        refreshed = session.scalar(select(FactSalesSellout).where(FactSalesSellout.source_key == sk))
        assert refreshed is not None
        assert refreshed.customer_id == c1
