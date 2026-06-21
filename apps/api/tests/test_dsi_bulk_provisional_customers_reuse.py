"""Bulk provisional customer apply: reuse approved alias scope (0048 idempotency)."""

from __future__ import annotations

import os
import secrets

import pytest
from sqlalchemy import func, inspect, select

from app.core.config import get_settings
from app.db.session_sync import SessionLocal
from app.models.dimensions import DimChannel, DimCustomer, DimRegion
from app.models.import_distributor_si import CustomerSourceTokenAlias, ImportEntityMappingCandidate
from app.models.ingestion import ImportJob, SourceDefinition
from app.services.commercial_planner.reference_bootstrap import ensure_commercial_planner_system_reference_data_sync
from app.services.imports.distributor_sales_inventory import _norm_key
from app.services.imports.dsi_bulk_provisional_customers_sync import run_dsi_bulk_provisional_customers_sync
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


def _require_dsi_tables_and_0048(session) -> int:
    names = set(inspect(session.connection()).get_table_names())
    if "import_entity_mapping_candidate" not in names:
        pytest.skip("DSI tables missing; apply Alembic through 20260430_0024.")
    indexes = inspect(session.connection()).get_indexes("customer_source_token_alias")
    if not any(i.get("name") == "uq_cust_src_token_alias_approved_scope" for i in indexes):
        pytest.skip("Requires migration 20260608_0048 (uq_cust_src_token_alias_approved_scope).")
    sid = session.scalar(select(SourceDefinition.id).where(SourceDefinition.code == "distributor_inventory"))
    assert sid is not None
    return int(sid)


def _seed_min_dims(session) -> tuple[int, int]:
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
    return int(region.id), int(channel.id)


def _make_customer_candidate(
    session,
    *,
    job_id: int,
    source_id: int,
    token: str,
    region_id: int,
    channel_id: int,
) -> ImportEntityMappingCandidate:
    cand = ImportEntityMappingCandidate(
        import_job_id=job_id,
        source_definition_id=source_id,
        entity_type="customer_dealer_token",
        normalized_key=_norm_key(token)[:512],
        dealer_group_token=None,
        row_count=1,
        sample_raw_values=[token],
        context={"source_customer_name_raw_samples": [token]},
        status="needs_review",
    )
    session.add(cand)
    session.flush()
    return cand


def _alias_count_for_scope(session, *, normalized_token: str, source_id: int) -> int:
    return int(
        session.scalar(
            select(func.count())
            .select_from(CustomerSourceTokenAlias)
            .where(
                CustomerSourceTokenAlias.status == "approved",
                CustomerSourceTokenAlias.normalized_token == normalized_token,
                CustomerSourceTokenAlias.source_definition_id == source_id,
            )
        )
        or 0
    )


@pytest.fixture()
def dsi_bulk_reuse_ctx() -> dict:
    _require_disposable_or_opt_in_db()
    with SessionLocal() as session:
        source_id = _require_dsi_tables_and_0048(session)
        region_id, channel_id = _seed_min_dims(session)
        job = ImportJob(
            source_id=source_id,
            template_slug="distributor_inventory",
            import_mode="validate",
            status="validated",
            stage="validated",
            file_name="bulk_reuse_test.csv",
        )
        session.add(job)
        session.commit()
        return {
            "source_id": source_id,
            "job_id": int(job.id),
            "region_id": region_id,
            "channel_id": channel_id,
        }


def test_bulk_provisional_reuses_existing_approved_alias(dsi_bulk_reuse_ctx: dict) -> None:
    token = f"Reuse Dealer {secrets.token_hex(4)}"
    nt = _norm_key(token)
    source_id = dsi_bulk_reuse_ctx["source_id"]
    job_id = dsi_bulk_reuse_ctx["job_id"]

    with SessionLocal() as session:
        keeper = DimCustomer(
            code=f"KEEP-{secrets.token_hex(3).upper()}",
            name=f"Keeper {token}",
            customer_status="unverified",
            region_id=dsi_bulk_reuse_ctx["region_id"],
            channel_id=dsi_bulk_reuse_ctx["channel_id"],
        )
        session.add(keeper)
        session.flush()
        session.add(
            CustomerSourceTokenAlias(
                customer_id=keeper.id,
                source_definition_id=source_id,
                distributor_id=None,
                raw_token=token,
                normalized_token=nt,
                status="approved",
                notes="pre-existing approved alias",
            )
        )
        cand = _make_customer_candidate(
            session,
            job_id=job_id,
            source_id=source_id,
            token=token,
            region_id=dsi_bulk_reuse_ctx["region_id"],
            channel_id=dsi_bulk_reuse_ctx["channel_id"],
        )
        cand_id = cand.id
        keeper_id = keeper.id
        before_aliases = _alias_count_for_scope(session, normalized_token=nt, source_id=source_id)
        session.commit()

    with SessionLocal() as session:
        out = run_dsi_bulk_provisional_customers_sync(
            session,
            job_id,
            {
                "candidate_ids": [cand_id],
                "region_id": dsi_bulk_reuse_ctx["region_id"],
                "channel_id": dsi_bulk_reuse_ctx["channel_id"],
            },
        )
        after_aliases = _alias_count_for_scope(session, normalized_token=nt, source_id=source_id)
        cand2 = session.get(ImportEntityMappingCandidate, cand_id)

    assert out["counts"] == {"created": 0, "reused": 1, "skipped": 0}
    assert out["applied"] == 1
    assert after_aliases == before_aliases
    assert cand2 is not None
    assert cand2.status == "resolved"
    assert cand2.suggested_entity_id == keeper_id
    assert cand2.match_reason == "steward_reused_approved_customer_alias"
    assert out["results"][0]["result"]["reused"] is True


def test_bulk_provisional_batch_dedupes_same_scope(dsi_bulk_reuse_ctx: dict) -> None:
    token = f"Batch Dealer {secrets.token_hex(4)}"
    nt = _norm_key(token)
    source_id = dsi_bulk_reuse_ctx["source_id"]
    job_id = dsi_bulk_reuse_ctx["job_id"]

    with SessionLocal() as session:
        c1 = _make_customer_candidate(
            session,
            job_id=job_id,
            source_id=source_id,
            token=token,
            region_id=dsi_bulk_reuse_ctx["region_id"],
            channel_id=dsi_bulk_reuse_ctx["channel_id"],
        )
        c1.normalized_key = f"{_norm_key(token)}-agg-a"[:512]
        c2 = ImportEntityMappingCandidate(
            import_job_id=job_id,
            source_definition_id=source_id,
            entity_type="customer_dealer_token",
            normalized_key=f"{_norm_key(token)}-agg-b"[:512],
            dealer_group_token=None,
            row_count=2,
            sample_raw_values=[token],
            context={"source_customer_name_raw_samples": [token]},
            status="needs_review",
        )
        session.add(c2)
        session.flush()
        id1, id2 = c1.id, c2.id
        session.commit()

    with SessionLocal() as session:
        out = run_dsi_bulk_provisional_customers_sync(
            session,
            job_id,
            {
                "candidate_ids": [id1, id2],
                "region_id": dsi_bulk_reuse_ctx["region_id"],
                "channel_id": dsi_bulk_reuse_ctx["channel_id"],
            },
        )
        alias_n = _alias_count_for_scope(session, normalized_token=nt, source_id=source_id)
        cust_ids = {
            session.get(ImportEntityMappingCandidate, id1).suggested_entity_id,
            session.get(ImportEntityMappingCandidate, id2).suggested_entity_id,
        }

    assert out["counts"] == {"created": 1, "reused": 1, "skipped": 0}
    assert out["applied"] == 2
    assert alias_n == 1
    assert len(cust_ids) == 1
    assert None not in cust_ids


def test_bulk_provisional_creates_fresh_candidate(dsi_bulk_reuse_ctx: dict) -> None:
    token = f"Fresh Dealer {secrets.token_hex(4)}"
    nt = _norm_key(token)
    source_id = dsi_bulk_reuse_ctx["source_id"]
    job_id = dsi_bulk_reuse_ctx["job_id"]

    with SessionLocal() as session:
        cand = _make_customer_candidate(
            session,
            job_id=job_id,
            source_id=source_id,
            token=token,
            region_id=dsi_bulk_reuse_ctx["region_id"],
            channel_id=dsi_bulk_reuse_ctx["channel_id"],
        )
        cand_id = cand.id
        session.commit()

    with SessionLocal() as session:
        out = run_dsi_bulk_provisional_customers_sync(
            session,
            job_id,
            {
                "candidate_ids": [cand_id],
                "region_id": dsi_bulk_reuse_ctx["region_id"],
                "channel_id": dsi_bulk_reuse_ctx["channel_id"],
            },
        )
        alias_n = _alias_count_for_scope(session, normalized_token=nt, source_id=source_id)
        cand2 = session.get(ImportEntityMappingCandidate, cand_id)

    assert out["counts"] == {"created": 1, "reused": 0, "skipped": 0}
    assert out["applied"] == 1
    assert alias_n == 1
    assert cand2 is not None
    assert cand2.status == "resolved"
    assert cand2.match_reason == "steward_created_provisional_customer"
    assert out["results"][0]["result"].get("created") is True
