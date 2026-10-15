"""N-0095 (BACKLOG-081 + 083): a confirmed customer merge seals the merged names to the keeper,
related-name groups merge through the same path, and the backfill seals past merges.

One rolled-back transaction; cip_test only.
"""

from __future__ import annotations

import secrets

import pytest
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.sync_url import sqlalchemy_sync_engine_url
from app.models.dimensions import DimCustomer
from app.models.import_distributor_si import CustomerSourceTokenAlias
from app.models.platform_audit import PlatformAuditEvent
from app.services.commercial_planner.open_channel_customer import OPEN_CHANNEL_CUSTOMER_CODE
from app.services.customer_full_merge import CustomerFullMergeError, confirm_customer_full_merge_sync
from app.services.customer_merge_alias_seal import (
    backfill_merged_customer_alias_seals,
    loser_alias_keys,
    seal_loser_display_name_aliases,
)
from app.services.customer_related_master_groups import (
    RELATED_SIMILARITY_KEY_PREFIX,
    related_group_members_for_key,
)
from app.services.imports.dsi_customer_name_normalization import normalize_customer_name_for_similarity


@pytest.fixture
def db():
    engine = create_engine(sqlalchemy_sync_engine_url(get_settings().database_url_sync))
    with engine.connect() as conn:
        if conn.execute(text("select current_database()")).scalar() != "cip_test":
            pytest.skip("cip_test only")
        conn.rollback()
        outer = conn.begin()
        session = Session(bind=conn, join_transaction_mode="create_savepoint")
        try:
            yield session
        finally:
            session.close()
            outer.rollback()
    engine.dispose()


def _tag() -> str:
    return secrets.token_hex(4)


def _customer(db: Session, name: str, *, code: str | None = None, merged_into: int | None = None) -> DimCustomer:
    row = DimCustomer(
        code=code or f"TMP-CUST-N0095-{secrets.token_hex(5)}",
        name=name,
        customer_status="merged" if merged_into else "active",
        merged_into_customer_id=merged_into,
    )
    db.add(row)
    db.flush()
    return row


def _global_aliases(db: Session, token: str) -> list[CustomerSourceTokenAlias]:
    return list(
        db.scalars(
            select(CustomerSourceTokenAlias).where(
                CustomerSourceTokenAlias.normalized_token == token,
                CustomerSourceTokenAlias.status == "approved",
                CustomerSourceTokenAlias.source_definition_id.is_(None),
                CustomerSourceTokenAlias.distributor_id.is_(None),
            )
        ).all()
    )


def _alias(db: Session, customer_id: int, token: str) -> CustomerSourceTokenAlias:
    row = CustomerSourceTokenAlias(
        customer_id=customer_id, raw_token=token, normalized_token=token, status="approved", notes="n0095 test"
    )
    db.add(row)
    db.flush()
    return row


def test_loser_alias_keys_cover_both_resolver_keys() -> None:
    assert loser_alias_keys("Zeta (Pty) Ltd") == ["zeta pty ltd", "zeta (pty) ltd"]
    assert loser_alias_keys("Amazon") == ["amazon"]
    assert loser_alias_keys("   ") == []


def test_confirmed_merge_seals_loser_name_under_both_keys(db: Session) -> None:
    t = _tag()
    keeper = _customer(db, f"Zeta{t} Pty Ltd")
    loser = _customer(db, f"Zeta{t} (Pty) Ltd")
    key = normalize_customer_name_for_similarity(keeper.name)
    assert key == normalize_customer_name_for_similarity(loser.name)
    db.commit()

    out = confirm_customer_full_merge_sync(
        db, similarity_key=key, survivor_id=keeper.id, audit_note="n0095 seal", performed_by="tester"
    )

    assert out["soft_redirected_customer_ids"] == [loser.id]
    tokens = {m["normalized_token"] for m in out["alias_seal_minted"]}
    assert tokens == {f"zeta{t} pty ltd", f"zeta{t} (pty) ltd"}
    for token in tokens:
        rows = _global_aliases(db, token)
        assert [r.customer_id for r in rows] == [keeper.id]
        assert rows[0].created_from_import_job_id is None
    db.refresh(loser)
    assert loser.merged_into_customer_id == keeper.id
    event = db.scalar(
        select(PlatformAuditEvent).where(
            PlatformAuditEvent.action == "customer_merge", PlatformAuditEvent.target_id == str(keeper.id)
        )
    )
    assert event is not None and event.actor == "tester"
    assert event.detail_json["alias_seal"]["minted"] == 2


def test_seal_is_idempotent(db: Session) -> None:
    t = _tag()
    keeper = _customer(db, f"Iota{t} Keeper")
    loser = _customer(db, f"Iota{t}", merged_into=keeper.id)
    first = seal_loser_display_name_aliases(db, keeper_id=keeper.id, loser_ids=[loser.id], audit_note="x")
    second = seal_loser_display_name_aliases(db, keeper_id=keeper.id, loser_ids=[loser.id], audit_note="x")
    assert len(first["alias_seal_minted"]) == 1
    assert second["alias_seal_minted"] == []
    assert [s["reason"] for s in second["alias_seal_skipped"]] == ["already_sealed"]
    assert len(_global_aliases(db, f"iota{t}")) == 1


def test_third_party_alias_is_reported_not_overwritten_and_merge_completes(db: Session) -> None:
    t = _tag()
    keeper = _customer(db, f"Theta{t} Pty Ltd")
    loser = _customer(db, f"Theta{t} (Pty) Ltd")
    third = _customer(db, f"Other{t}")
    taken = _alias(db, third.id, f"theta{t} pty ltd")
    db.commit()

    out = confirm_customer_full_merge_sync(
        db,
        similarity_key=normalize_customer_name_for_similarity(keeper.name),
        survivor_id=keeper.id,
        audit_note="n0095 conflict",
    )

    assert out["soft_redirected_customer_ids"] == [loser.id]
    assert [c["existing_customer_id"] for c in out["alias_seal_conflicts"]] == [third.id]
    db.refresh(taken)
    assert taken.customer_id == third.id
    assert [r.customer_id for r in _global_aliases(db, f"theta{t} (pty) ltd")] == [keeper.id]


def test_alias_left_on_loser_moves_to_keeper(db: Session) -> None:
    t = _tag()
    keeper = _customer(db, f"Rho{t} Keeper")
    loser = _customer(db, f"Rho{t}", merged_into=keeper.id)
    stale = _alias(db, loser.id, f"rho{t}")
    out = seal_loser_display_name_aliases(db, keeper_id=keeper.id, loser_ids=[loser.id], audit_note="x")
    assert [r["alias_id"] for r in out["alias_seal_reassigned"]] == [stale.id]
    db.refresh(stale)
    assert stale.customer_id == keeper.id


def test_open_channel_is_never_sealed(db: Session) -> None:
    oc = db.scalar(select(DimCustomer).where(DimCustomer.code == OPEN_CHANNEL_CUSTOMER_CODE))
    if oc is None:
        pytest.skip("no OPEN_CHANNEL row on cip_test")
    t = _tag()
    other = _customer(db, f"Sigma{t}")
    into_oc = seal_loser_display_name_aliases(db, keeper_id=oc.id, loser_ids=[other.id], audit_note="x")
    from_oc = seal_loser_display_name_aliases(db, keeper_id=other.id, loser_ids=[oc.id], audit_note="x")
    assert into_oc["alias_seal_minted"] == [] and from_oc["alias_seal_minted"] == []
    assert {s["reason"] for s in into_oc["alias_seal_skipped"] + from_oc["alias_seal_skipped"]} == {
        "open_channel_excluded"
    }


def test_related_name_subset_merges_and_seals(db: Session) -> None:
    t = _tag()
    short = _customer(db, f"Kappa{t}")
    long = _customer(db, f"Kappa{t} Commercial Services (South Africa)")
    unrelated = _customer(db, f"Kappa{t} Holdings")
    db.commit()
    anchor = normalize_customer_name_for_similarity(short.name)
    members = {m.id for m in related_group_members_for_key(db, anchor)}
    assert {short.id, long.id, unrelated.id} <= members

    with pytest.raises(CustomerFullMergeError):
        confirm_customer_full_merge_sync(
            db,
            similarity_key=f"{RELATED_SIMILARITY_KEY_PREFIX}{anchor}",
            survivor_id=long.id,
            audit_note="x",
            customer_ids=[long.id],
        )

    out = confirm_customer_full_merge_sync(
        db,
        similarity_key=f"{RELATED_SIMILARITY_KEY_PREFIX}{anchor}",
        survivor_id=long.id,
        audit_note="n0095 related",
        customer_ids=[short.id, long.id],
    )
    assert out["soft_redirected_customer_ids"] == [short.id]
    assert [r.customer_id for r in _global_aliases(db, f"kappa{t}")] == [long.id]
    db.refresh(unrelated)
    assert unrelated.merged_into_customer_id is None


def test_related_group_leaves_out_test_fixture_customers(db: Session) -> None:
    t = _tag()
    real = _customer(db, f"Lambda{t}")
    real_long = _customer(db, f"Lambda{t} Trading")
    fixture = _customer(db, f"Lambda{t} Fixture Co", code=f"C-REL-B-{t}")
    db.commit()
    members = {m.id for m in related_group_members_for_key(db, normalize_customer_name_for_similarity(real.name))}
    assert {real.id, real_long.id} <= members
    assert fixture.id not in members


def test_backfill_seals_past_merges_once_and_skips_fixtures(db: Session) -> None:
    t = _tag()
    keeper = _customer(db, f"Omega{t} Keeper", code=f"CUST-N0095-{t}")
    _customer(db, f"Omega{t}", merged_into=keeper.id)
    fixture_keeper = _customer(db, f"Psi{t} Keeper", code=f"C-FULL-K-{t}")
    _customer(db, f"Psi{t}", code=f"C-FULL-L-{t}", merged_into=fixture_keeper.id)
    db.commit()

    dry = backfill_merged_customer_alias_seals(db, dry_run=True)
    assert any(m["normalized_token"] == f"omega{t}" for m in dry["alias_seal_minted"])
    assert not any(m["normalized_token"] == f"psi{t}" for m in dry["alias_seal_minted"])
    assert dry["test_fixture_merges_left_untouched"] >= 1
    assert _global_aliases(db, f"omega{t}") == []

    applied = backfill_merged_customer_alias_seals(db, dry_run=False)
    assert any(m["normalized_token"] == f"omega{t}" for m in applied["alias_seal_minted"])
    assert [r.customer_id for r in _global_aliases(db, f"omega{t}")] == [keeper.id]
    assert _global_aliases(db, f"psi{t}") == []

    again = backfill_merged_customer_alias_seals(db, dry_run=False)
    assert not any(m["normalized_token"] == f"omega{t}" for m in again["alias_seal_minted"])
