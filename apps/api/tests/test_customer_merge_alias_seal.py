"""Tests for merge alias seal + DSI merge-redirect follow."""

from __future__ import annotations

import os
import secrets

import pytest
from sqlalchemy import select

from app.core.config import get_settings
from app.db.session_sync import SessionLocal
from app.models.dimensions import DimCustomer
from app.models.import_distributor_si import CustomerSourceTokenAlias
from app.services.customer_full_merge import confirm_customer_full_merge_sync
from app.services.customer_merge_redirect import follow_customer_merge_redirect
from app.services.imports.distributor_sales_inventory import (
    _build_resolution_cache,
    _resolve_customer,
    _resolve_customer_from_cache,
)
from app.services.imports.dsi_customer_name_normalization import normalize_customer_name_for_similarity
from app.services.imports.provisional_entity_identity import customer_source_token_alias_key
from app.services.commercial_planner.reference_bootstrap import ensure_commercial_planner_system_reference_data_sync
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


def _seed_core(session) -> None:
    _seed_import_core(session)
    ensure_commercial_planner_system_reference_data_sync(session.connection())


def test_follow_customer_merge_redirect_unit() -> None:
    assert follow_customer_merge_redirect  # import smoke
    m = {1: 2, 2: 3, 3: None}
    from app.services.customer_merge_redirect import terminal_customer_id_from_map

    assert terminal_customer_id_from_map(m, 1) == 3
    assert terminal_customer_id_from_map(m, 3) == 3


def test_full_merge_seals_loser_name_alias_and_resolve_follows() -> None:
    _require_disposable_or_opt_in_db()
    with SessionLocal() as session:
        _seed_core(session)
        token = secrets.token_hex(4)
        survivor_name = f"Seal Survivor {token}"
        loser_name = f"Seal Survivor {token} Branch COD"
        # Exact-key pair via legal suffix so name-similarity merge works.
        c1 = DimCustomer(code=f"C-SEAL-A-{token}", name=survivor_name, customer_status="active")
        c2 = DimCustomer(
            code=f"C-SEAL-B-{token}",
            name=f"{survivor_name} Ltd",
            customer_status="unverified",
        )
        # Related-style loser with different similarity key (containment).
        c3 = DimCustomer(code=f"C-SEAL-C-{token}", name=loser_name, customer_status="unverified")
        session.add_all([c1, c2, c3])
        session.commit()
        sid, lid_exact, lid_related = int(c1.id), int(c2.id), int(c3.id)
        exact_key = normalize_customer_name_for_similarity(survivor_name)

        out_exact = confirm_customer_full_merge_sync(
            session,
            similarity_key=exact_key,
            survivor_id=sid,
            audit_note="seal exact",
            customer_ids=[sid, lid_exact],
        )
        assert out_exact["survivor_id"] == sid
        assert any(m["loser_id"] == lid_exact for m in out_exact["alias_seal_minted"])

        related_key = f"related:{normalize_customer_name_for_similarity(survivor_name)}"
        # Re-load survivor after commit; related group needs unmerged members only.
        # c3 still unmerged; anchor is survivor name which equals survivor_name key.
        # After exact merge, survivor remains; related group is survivor + c3.
        out_rel = confirm_customer_full_merge_sync(
            session,
            similarity_key=related_key,
            survivor_id=sid,
            audit_note="seal related",
            customer_ids=[sid, lid_related],
        )
        assert any(m["loser_id"] == lid_related for m in out_rel["alias_seal_minted"])
        assert out_rel["alias_seal_conflicts"] == []

        alias_nt = customer_source_token_alias_key(loser_name)
        alias = session.scalars(
            select(CustomerSourceTokenAlias).where(
                CustomerSourceTokenAlias.customer_id == sid,
                CustomerSourceTokenAlias.normalized_token == alias_nt,
                CustomerSourceTokenAlias.status == "approved",
            )
        ).first()
        assert alias is not None

        # Idempotent re-seal: preview-only path not needed; second seal via helper.
        from app.services.customer_merge_alias_seal import seal_loser_display_name_aliases

        again = seal_loser_display_name_aliases(
            session, keeper_id=sid, loser_ids=[lid_related], audit_note="idempotent"
        )
        assert again["alias_seal_minted"] == []
        assert any(s.get("reason") == "already_sealed" for s in again["alias_seal_skipped"])
        session.rollback()

        # Resolve by sealed loser name → survivor
        cid, diags = _resolve_customer(
            session,
            source_id=None,
            distributor_id=None,
            customer_raw=loser_name,
            dealer_group_raw=None,
            channel_raw=None,
            open_flag_raw=None,
        )
        assert cid == sid
        assert "customer_resolved_alias" in diags or "customer_redirect_followed" in diags

        # Resolve by loser code → survivor via redirect
        loser = session.get(DimCustomer, lid_related)
        assert loser is not None
        cid2, diags2 = _resolve_customer(
            session,
            source_id=None,
            distributor_id=None,
            customer_raw=loser.code,
            dealer_group_raw=None,
            channel_raw=None,
            open_flag_raw=None,
        )
        assert cid2 == sid
        assert "customer_redirect_followed" in diags2

        cache = _build_resolution_cache(session, None)
        cid3, diags3 = _resolve_customer_from_cache(
            source_id=None,
            distributor_id=None,
            customer_raw=loser_name,
            dealer_group_raw=None,
            channel_raw=None,
            open_flag_raw=None,
            res_cache=cache,
        )
        assert cid3 == sid


def test_alias_seal_conflict_reports_third_party() -> None:
    _require_disposable_or_opt_in_db()
    with SessionLocal() as session:
        _seed_core(session)
        token = secrets.token_hex(4)
        other = DimCustomer(code=f"C-OTH-{token}", name=f"Other Owner {token}", customer_status="active")
        survivor = DimCustomer(code=f"C-SRV-{token}", name=f"Conflict Surv {token}", customer_status="active")
        loser = DimCustomer(
            code=f"C-LOS-{token}",
            name=f"Conflict Surv {token} Ltd",
            customer_status="unverified",
        )
        session.add_all([other, survivor, loser])
        session.flush()
        # Pre-seed global alias for loser's sealed key onto a third party.
        from app.services.imports.dsi_customer_alias_scope import (
            insert_approved_customer_alias_on_conflict_do_nothing,
        )

        loser_name = f"Conflict Surv {token} Ltd"
        nt = customer_source_token_alias_key(loser_name)
        insert_approved_customer_alias_on_conflict_do_nothing(
            session,
            customer_id=int(other.id),
            raw_token=loser_name,
            normalized_token=nt,
            source_definition_id=None,
            distributor_id=None,
            dealer_group_token=None,
            notes="third party",
        )
        session.commit()

        key = normalize_customer_name_for_similarity(f"Conflict Surv {token}")
        out = confirm_customer_full_merge_sync(
            session,
            similarity_key=key,
            survivor_id=int(survivor.id),
            audit_note="conflict seal",
            customer_ids=[int(survivor.id), int(loser.id)],
        )
        assert out["soft_redirected_customer_ids"] == [int(loser.id)]
        assert any(
            c.get("existing_customer_id") == int(other.id) for c in out["alias_seal_conflicts"]
        )
        # Third-party alias untouched
        still = session.scalars(
            select(CustomerSourceTokenAlias).where(
                CustomerSourceTokenAlias.normalized_token == nt,
                CustomerSourceTokenAlias.customer_id == int(other.id),
            )
        ).first()
        assert still is not None
