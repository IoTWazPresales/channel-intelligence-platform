"""Bulk map customer apply: reuse approved alias scope (0048 idempotency)."""

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
from app.services.imports.dsi_bulk_map_customers_sync import run_dsi_bulk_map_customers_sync
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
    normalized_key_suffix: str | None = None,
    dealer_group_token: str | None = None,
    normalized_key_override: str | None = None,
) -> ImportEntityMappingCandidate:
    nk = _norm_key(token)[:512]
    if normalized_key_override is not None:
        nk = normalized_key_override[:512]
    elif normalized_key_suffix:
        nk = f"{nk}-{normalized_key_suffix}"[:512]
    cand = ImportEntityMappingCandidate(
        import_job_id=job_id,
        source_definition_id=source_id,
        entity_type="customer_dealer_token",
        normalized_key=nk,
        dealer_group_token=dealer_group_token,
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
def dsi_bulk_map_ctx() -> dict:
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
            file_name="bulk_map_scope_test.csv",
        )
        session.add(job)
        session.commit()
        return {
            "source_id": source_id,
            "job_id": int(job.id),
            "region_id": region_id,
            "channel_id": channel_id,
        }


def test_bulk_map_distinct_candidates_key_alias_on_resolution_identity(dsi_bulk_map_ctx: dict) -> None:
    """Two distinct candidates map to one customer; each alias is keyed on the candidate
    resolution identity (normalized_key), not the customer-name evidence. No UniqueViolation."""
    token = f"Res Q IT Map {secrets.token_hex(4)}"
    nt = _norm_key(token)
    nt_a = f"{nt}-a"[:512]
    nt_b = f"{nt}-b"[:512]
    source_id = dsi_bulk_map_ctx["source_id"]
    job_id = dsi_bulk_map_ctx["job_id"]

    with SessionLocal() as session:
        target = DimCustomer(
            code=f"MAP-{secrets.token_hex(3).upper()}",
            name=f"Target {token}",
            customer_status="verified",
            region_id=dsi_bulk_map_ctx["region_id"],
            channel_id=dsi_bulk_map_ctx["channel_id"],
        )
        session.add(target)
        session.flush()
        c1 = _make_customer_candidate(
            session,
            job_id=job_id,
            source_id=source_id,
            token=token,
            region_id=dsi_bulk_map_ctx["region_id"],
            channel_id=dsi_bulk_map_ctx["channel_id"],
            normalized_key_suffix="a",
        )
        c2 = _make_customer_candidate(
            session,
            job_id=job_id,
            source_id=source_id,
            token=token,
            region_id=dsi_bulk_map_ctx["region_id"],
            channel_id=dsi_bulk_map_ctx["channel_id"],
            normalized_key_suffix="b",
        )
        target_id = int(target.id)
        id1, id2 = c1.id, c2.id
        session.commit()

    with SessionLocal() as session:
        out = run_dsi_bulk_map_customers_sync(
            session,
            job_id,
            customer_id=target_id,
            candidate_ids=[id1, id2],
        )
        # Alias is keyed on the candidate resolution identity (normalized_key), so the
        # customer-name scope must NOT be used as the lookup key.
        assert _alias_count_for_scope(session, normalized_token=nt, source_id=source_id) == 0
        assert _alias_count_for_scope(session, normalized_token=nt_a, source_id=source_id) == 1
        assert _alias_count_for_scope(session, normalized_token=nt_b, source_id=source_id) == 1
        cand1 = session.get(ImportEntityMappingCandidate, id1)
        cand2 = session.get(ImportEntityMappingCandidate, id2)

    assert out["applied"] == 2
    assert out["failed"] == 0
    assert cand1 is not None and cand2 is not None
    assert cand1.status == "resolved"
    assert cand2.status == "resolved"
    assert cand1.suggested_entity_id == target_id
    assert cand2.suggested_entity_id == target_id
    reasons = {cand1.match_reason, cand2.match_reason}
    assert "steward_map_existing_customer" in reasons or "steward_reused_approved_customer_alias" in reasons


def test_bulk_map_keys_alias_on_dealer_group_not_customer_name(dsi_bulk_map_ctx: dict) -> None:
    """Regression: when a candidate carries a Dealer Name Group, the approved alias must be
    keyed on the dealer-group resolution token (== normalized_key) so DSI staging resolution
    finds it. Keying on the customer-name column was the root cause of permanent
    customer_unresolved blockers (job #96)."""
    suffix = secrets.token_hex(4)
    dealer_group = f"NEVILLE HAMMAN COMPUTERS CC T/A FURNWORLD {suffix}"
    customer_name = f"Neville Hamman Computers t/a Furnworld Computers {suffix}"
    nk = _norm_key(dealer_group)[:512]
    customer_name_key = _norm_key(customer_name)[:512]
    source_id = dsi_bulk_map_ctx["source_id"]
    job_id = dsi_bulk_map_ctx["job_id"]

    with SessionLocal() as session:
        target = DimCustomer(
            code=f"DG-{secrets.token_hex(3).upper()}",
            name=dealer_group,
            customer_status="verified",
            region_id=dsi_bulk_map_ctx["region_id"],
            channel_id=dsi_bulk_map_ctx["channel_id"],
        )
        session.add(target)
        session.flush()
        cand = _make_customer_candidate(
            session,
            job_id=job_id,
            source_id=source_id,
            token=customer_name,
            region_id=dsi_bulk_map_ctx["region_id"],
            channel_id=dsi_bulk_map_ctx["channel_id"],
            dealer_group_token=dealer_group,
            normalized_key_override=nk,
        )
        target_id = int(target.id)
        cand_id = cand.id
        session.commit()

    with SessionLocal() as session:
        out = run_dsi_bulk_map_customers_sync(
            session,
            job_id,
            customer_id=target_id,
            candidate_ids=[cand_id],
        )
        # Alias keyed on dealer-group resolution identity, NOT the customer-name column.
        alias = session.scalars(
            select(CustomerSourceTokenAlias).where(
                CustomerSourceTokenAlias.status == "approved",
                CustomerSourceTokenAlias.customer_id == target_id,
            )
        ).all()

    assert out["applied"] == 1
    assert out["failed"] == 0
    assert len(alias) == 1
    assert alias[0].normalized_token == nk
    assert alias[0].normalized_token != customer_name_key


def test_bulk_map_reuses_existing_approved_alias(dsi_bulk_map_ctx: dict) -> None:
    token = f"Existing Map {secrets.token_hex(4)}"
    nt = _norm_key(token)
    source_id = dsi_bulk_map_ctx["source_id"]
    job_id = dsi_bulk_map_ctx["job_id"]

    with SessionLocal() as session:
        keeper = DimCustomer(
            code=f"KEEP-{secrets.token_hex(3).upper()}",
            name=f"Keeper {token}",
            customer_status="verified",
            region_id=dsi_bulk_map_ctx["region_id"],
            channel_id=dsi_bulk_map_ctx["channel_id"],
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
            region_id=dsi_bulk_map_ctx["region_id"],
            channel_id=dsi_bulk_map_ctx["channel_id"],
        )
        cand_id = cand.id
        keeper_id = int(keeper.id)
        before_aliases = _alias_count_for_scope(session, normalized_token=nt, source_id=source_id)
        session.commit()

    with SessionLocal() as session:
        out = run_dsi_bulk_map_customers_sync(
            session,
            job_id,
            customer_id=keeper_id,
            candidate_ids=[cand_id],
        )
        after_aliases = _alias_count_for_scope(session, normalized_token=nt, source_id=source_id)
        cand2 = session.get(ImportEntityMappingCandidate, cand_id)

    assert out["applied"] == 1
    assert after_aliases == before_aliases
    assert cand2 is not None
    assert cand2.status == "resolved"
    assert cand2.suggested_entity_id == keeper_id
    assert cand2.match_reason == "steward_reused_approved_customer_alias"
    assert out["results"][0]["result"]["reused"] is True
