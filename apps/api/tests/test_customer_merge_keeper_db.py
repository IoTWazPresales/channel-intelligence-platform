"""N-0095: changing which record keeps a past merge (the steward picks; nothing picks for them).

One rolled-back transaction; cip_test only.
"""

from __future__ import annotations

import asyncio
import secrets

import pytest
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.sync_url import sqlalchemy_sync_engine_url
from app.models.dimensions import CustomerContact, DimCustomer
from app.models.import_distributor_si import CustomerSourceTokenAlias
from app.models.platform_audit import PlatformAuditEvent
from app.services.commercial_planner.open_channel_customer import OPEN_CHANNEL_CUSTOMER_CODE
from app.services.customer_merge_keeper import (
    CustomerKeeperChangeError,
    confirm_change_keeper,
    merged_at_from_keeper_notes,
    preview_change_keeper,
)
from app.services.imports.distributor_sales_inventory import _resolve_customer


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


def _customer(db: Session, name: str, *, code: str, merged_into: int | None = None, status: str = "active") -> DimCustomer:
    row = DimCustomer(code=code, name=name, customer_status=status, merged_into_customer_id=merged_into)
    db.add(row)
    db.flush()
    return row


@pytest.fixture
def merged_pair(db: Session):
    """Keeper (promoted) with two merged records, one alias and one contact on the keeper."""
    t = secrets.token_hex(4)
    keeper = _customer(db, f"Delta{t} Commercial Services", code=f"CUST-N0095-{t}")
    old = _customer(db, f"Delta{t}", code=f"TMP-CUST-N0095-{t}-A", merged_into=keeper.id, status="merged")
    other = _customer(db, f"Delta{t} SA", code=f"TMP-CUST-N0095-{t}-B", merged_into=keeper.id, status="merged")
    alias = CustomerSourceTokenAlias(
        customer_id=keeper.id, raw_token=f"Delta{t}", normalized_token=f"delta{t}", status="approved", notes="seal"
    )
    contact = CustomerContact(customer_id=keeper.id, contact_name="Buyer", contact_role="general")
    db.add_all([alias, contact])
    db.commit()
    return {"t": t, "keeper": keeper, "old": old, "other": other, "alias": alias, "contact": contact}


def test_preview_lists_rows_and_records_and_writes_nothing(db: Session, merged_pair) -> None:
    keeper, old, other = merged_pair["keeper"], merged_pair["old"], merged_pair["other"]
    plan = preview_change_keeper(db, current_keeper_id=keeper.id, new_keeper_id=old.id, audit_note="look")
    assert plan["rows_to_move"] >= 2
    assert plan["rows_to_move_by_table"]["customer_contact.customer_id"] == 1
    assert plan["other_merged_records_redirected"] == [other.id]
    assert plan["new_keeper_status_after"] == "active"
    db.expire_all()
    assert db.get(DimCustomer, old.id).merged_into_customer_id == keeper.id


def test_confirm_moves_everything_to_the_chosen_keeper(db: Session, merged_pair) -> None:
    t = merged_pair["t"]
    keeper, old, other = merged_pair["keeper"], merged_pair["old"], merged_pair["other"]
    out = confirm_change_keeper(
        db, current_keeper_id=keeper.id, new_keeper_id=old.id, audit_note="steward picked", performed_by="tester"
    )
    assert out["new_keeper_id"] == old.id and out["previous_keeper_id"] == keeper.id
    db.expire_all()
    new = db.get(DimCustomer, old.id)
    prev = db.get(DimCustomer, keeper.id)
    assert new.merged_into_customer_id is None and new.customer_status == "active"
    assert new.code == old.code and new.name == f"Delta{t}"
    assert prev.merged_into_customer_id == old.id and prev.customer_status == "merged"
    assert db.get(DimCustomer, other.id).merged_into_customer_id == old.id
    assert db.get(CustomerContact, merged_pair["contact"].id).customer_id == old.id
    assert db.get(CustomerSourceTokenAlias, merged_pair["alias"].id).customer_id == old.id
    sealed = db.scalars(
        select(CustomerSourceTokenAlias.customer_id).where(
            CustomerSourceTokenAlias.normalized_token == f"delta{t} commercial services",
            CustomerSourceTokenAlias.source_definition_id.is_(None),
            CustomerSourceTokenAlias.distributor_id.is_(None),
        )
    ).all()
    assert list(sealed) == [old.id]
    event = db.scalar(select(PlatformAuditEvent).where(PlatformAuditEvent.action == "customer_change_keeper", PlatformAuditEvent.target_id == str(old.id)))
    assert event is not None and event.detail_json["previous_keeper_id"] == keeper.id
    # The resolver now lands every old name and code on the chosen keeper.
    for token in (keeper.name, keeper.code, other.name):
        cid, _diag = _resolve_customer(
            db, source_id=None, distributor_id=None, customer_raw=token,
            dealer_group_raw=None, channel_raw=None, open_flag_raw=None,
        )
        assert cid == old.id, token


def test_change_back_restores_the_original_keeper(db: Session, merged_pair) -> None:
    keeper, old = merged_pair["keeper"], merged_pair["old"]
    confirm_change_keeper(db, current_keeper_id=keeper.id, new_keeper_id=old.id, audit_note="swap")
    confirm_change_keeper(db, current_keeper_id=old.id, new_keeper_id=keeper.id, audit_note="swap back")
    db.expire_all()
    assert db.get(DimCustomer, keeper.id).merged_into_customer_id is None
    assert db.get(DimCustomer, old.id).merged_into_customer_id == keeper.id
    assert db.get(DimCustomer, merged_pair["other"].id).merged_into_customer_id == keeper.id
    assert db.get(CustomerContact, merged_pair["contact"].id).customer_id == keeper.id


def test_refuses_pairs_that_are_not_a_keeper_and_its_merged_record(db: Session, merged_pair) -> None:
    keeper, old, other = merged_pair["keeper"], merged_pair["old"], merged_pair["other"]
    with pytest.raises(CustomerKeeperChangeError, match="not a keeper"):
        preview_change_keeper(db, current_keeper_id=old.id, new_keeper_id=other.id, audit_note="x")
    stranger = _customer(db, "Stranger", code=f"CUST-N0095-{merged_pair['t']}-S")
    db.commit()
    with pytest.raises(CustomerKeeperChangeError, match="not merged into"):
        preview_change_keeper(db, current_keeper_id=keeper.id, new_keeper_id=stranger.id, audit_note="x")
    with pytest.raises(CustomerKeeperChangeError, match="audit_note"):
        preview_change_keeper(db, current_keeper_id=keeper.id, new_keeper_id=old.id, audit_note=" ")


def test_open_channel_stays_the_keeper(db: Session) -> None:
    oc = db.scalar(select(DimCustomer).where(DimCustomer.code == OPEN_CHANNEL_CUSTOMER_CODE))
    if oc is None:
        pytest.skip("no OPEN_CHANNEL row on cip_test")
    t = secrets.token_hex(4)
    absorbed = _customer(db, f"Open Channel {t}", code=f"TMP-CUST-N0095-{t}", merged_into=oc.id, status="merged")
    db.commit()
    with pytest.raises(CustomerKeeperChangeError, match="OPEN_CHANNEL stays the keeper"):
        preview_change_keeper(db, current_keeper_id=oc.id, new_keeper_id=absorbed.id, audit_note="x")


def test_merged_at_is_read_from_the_keeper_merge_note() -> None:
    notes = (
        "Provisional customer created from DSI import candidate 2130 (job 43).\n"
        "[customer-full merge 2026-07-11T14:36:27.052416+00:00] key=related:amazon; survivor=299; losers=[26]; by=steward; note=11"
    )
    assert merged_at_from_keeper_notes(notes, 26) == "2026-07-11T14:36:27.052416+00:00"
    assert merged_at_from_keeper_notes(notes, 2) is None


def test_past_merges_list_shows_both_sides_with_evidence() -> None:
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

    from app.services.customer_merge_keeper import list_past_merges

    t = secrets.token_hex(4)

    async def run() -> dict:
        engine = create_async_engine(get_settings().database_url)
        try:
            async with engine.connect() as conn:
                if (await conn.execute(text("select current_database()"))).scalar() != "cip_test":
                    pytest.skip("cip_test only")
                await conn.rollback()
                outer = await conn.begin()
                adb = AsyncSession(bind=conn, join_transaction_mode="create_savepoint")
                try:
                    keeper = DimCustomer(code=f"CUST-N0095-{t}", name=f"Mu{t} Commercial", customer_status="active")
                    adb.add(keeper)
                    await adb.flush()
                    old = DimCustomer(code=f"TMP-CUST-N0095-{t}", name=f"Mu{t}", customer_status="merged",
                                      merged_into_customer_id=keeper.id)
                    fixture = DimCustomer(code=f"C-FULL-{t}", name=f"Mu{t} Fixture", customer_status="merged",
                                          merged_into_customer_id=keeper.id)
                    adb.add_all([old, fixture])
                    await adb.flush()
                    adb.add(CustomerSourceTokenAlias(customer_id=keeper.id, raw_token=f"Mu{t}",
                                                     normalized_token=f"mu{t}", status="approved"))
                    await adb.flush()
                    return {"out": await list_past_merges(adb, q=f"mu{t}"), "keeper": keeper.id, "old": old.id}
                finally:
                    await adb.close()
                    await outer.rollback()
        finally:
            await engine.dispose()

    res = asyncio.run(run())
    out = res["out"]
    assert out["total"] == 1
    item = out["items"][0]
    assert item["keeper"]["id"] == res["keeper"]
    assert item["keeper"]["alias_count"] == 1 and item["keeper"]["aliases"] == [f"Mu{t}"]
    assert item["keeper"]["reference_rows"] >= 1
    assert [m["id"] for m in item["merged"]] == [res["old"]]
    assert item["merged"][0]["reference_rows"] == 0
    assert out["test_fixture_merges_excluded"] >= 1
