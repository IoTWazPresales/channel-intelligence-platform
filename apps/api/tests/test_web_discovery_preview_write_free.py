"""Preview writes nothing to the database, and the database enforces it. cip_test only.

The Preview runs in a ``SET TRANSACTION READ ONLY`` transaction that is rolled back. This test proves
it three ways: no recorded statement is a write, the row counts and ``updated_at`` of every table a
discovery run could touch are unchanged, and a write attempted inside a Preview is rejected by
Postgres itself (``ReadOnlySqlTransaction``), so the guard is real and not just untested code.

No network: the getter, DNS and search are fakes. Fictional names, ``.test`` hosts.
"""

from __future__ import annotations

import re
import uuid
from typing import Any

import pytest
from sqlalchemy import event, text
from sqlalchemy.exc import DBAPIError

from app.db.session_sync import SessionLocal
from app.models.customer_web_site import CustomerWebSite
from app.services.listing_capture.web_discovery import candidates as cand
from app.services.listing_capture.web_discovery import preview
from tests.web_discovery_db import ALPHA_HOST, World, committed_world  # noqa: F401
from tests.web_discovery_support import FakeSearch, FakeWeb, home_page, make_getter

WRITE = re.compile(r"^\s*(INSERT|UPDATE|DELETE|MERGE|CREATE|ALTER|DROP|TRUNCATE)\b", re.IGNORECASE)

_OWN_CUSTOMERS = "customer_id IN (SELECT id FROM dim_customer WHERE tenant_id = :t)"
SNAPSHOT_WHERE = {
    "customer_web_site": "tenant_id = :t",
    "listing_site": "tenant_id = :t",
    "listing_site_seller": "tenant_id = :t",
    "listing_link": "tenant_id = :t",
    "listing_link_queue": "tenant_id = :t",
    "cst_listing_seed": _OWN_CUSTOMERS,
    "customer_listing": _OWN_CUSTOMERS,
    "customer_report_config": _OWN_CUSTOMERS,
    "tenant_setting": "tenant_id = :t",
    "steward_audit_event": "tenant_id = :t",
}


def _snapshot(tenant: str) -> dict[str, tuple[Any, ...]]:
    """``(count, max(updated_at))`` per table, scoped to the test tenant."""
    out: dict[str, tuple[Any, ...]] = {}
    with SessionLocal() as session:
        for table, where in SNAPSHOT_WHERE.items():
            has_updated_at = session.execute(
                text("SELECT 1 FROM information_schema.columns WHERE table_name = :n AND column_name = 'updated_at'"),
                {"n": table},
            ).first()
            latest = "max(updated_at)" if has_updated_at else "NULL"
            row = session.execute(text(f"SELECT count(*), {latest} FROM {table} WHERE {where}"), {"t": tenant}).one()
            out[table] = tuple(row)
        session.rollback()
    return out


def _fake_world() -> tuple[FakeWeb, Any, FakeSearch, Any]:
    home = home_page("Alpha Gadgets", org="Alpha Gadgets")
    web = FakeWeb({f"https://{ALPHA_HOST}/": home, "https://typed.example.test/": home_page("Some shop")})
    hosts = {ALPHA_HOST, f"www.{ALPHA_HOST}"}

    def resolve(host: str) -> list[str]:
        return ["8.8.8.8"] if host in hosts else []

    search = FakeSearch({'"Widget One"': [ALPHA_HOST, "unrelated.example.test"]})
    return web, make_getter(web, resolve=resolve), search, resolve


def _run(world: World, request: dict[str, Any], getter, resolve, search) -> dict[str, Any]:
    """What the worker task does: its own session, then roll back."""
    with SessionLocal() as session:
        try:
            return preview.run_preview(
                session,
                tenant_id=world.tenant,
                preview_id=str(uuid.uuid4()),
                request=request,
                getter=getter,
                resolve=resolve,
                plan_store=preview.MemoryPlanStore(),
                search=search,
                engine_hosts=frozenset(),
            )
        finally:
            session.rollback()


def test_preview_writes_nothing_for_every_scope(committed_world: World) -> None:
    world = committed_world
    _web, getter, search, resolve = _fake_world()
    requests = [
        {"scope": "customer", "customer_id": world.alpha_id},
        {"scope": "customer", "customer_id": world.beta_id},
        {"scope": "reporting"},
        {"scope": "domain", "customer_id": world.alpha_id, "domain": "typed.example.test"},
        {"scope": "unlinked_listings", "customer_id": None},
    ]
    before = _snapshot(world.tenant)
    assert before["customer_listing"][0] == 1 and before["tenant_setting"][0] == 3

    with SessionLocal() as probe:
        engine = probe.get_bind()
    runs: list[list[str]] = []

    def record(_conn, _cursor, statement, _params, _context, _executemany) -> None:
        runs[-1].append(statement)

    event.listen(engine, "before_cursor_execute", record)
    plans = []
    try:
        for request in requests:
            runs.append([])
            plans.append(_run(world, request, getter, resolve, search))
    finally:
        event.remove(engine, "before_cursor_execute", record)

    assert [p["status"] for p in plans] == ["done"] * len(requests)
    for statements in runs:
        assert statements, "every preview runs at least the read-only statement"
        assert statements[0].strip().upper().startswith("SET TRANSACTION READ ONLY")
        assert [s for s in statements if WRITE.match(s)] == []
    assert _snapshot(world.tenant) == before


def test_the_preview_finds_the_customers_site_from_evidence(committed_world: World) -> None:
    world = committed_world
    _web, getter, search, resolve = _fake_world()
    plan = _run(world, {"scope": "customer", "customer_id": world.alpha_id}, getter, resolve, search)
    result = plan["result"]
    assert result["search"]["status"] == "ok" and result["search"]["provider_used"] == "ddg_html"
    (block,) = result["customers"]
    assert block["customer_name"] == "Alpha Gadgets (Pty) Ltd" and block["reporting"] is True
    by_domain = {c["domain"]: c for c in block["candidates"]}
    found = by_domain[ALPHA_HOST]
    assert found["outcome"] == "auto_accept"
    assert found["evidence"]["name_match"]["exact"] is True
    assert found["evidence"]["country_match"] == {"value": True, "how": "cctld"}
    assert found["evidence"]["product_search_hits"][0]["product_id"] == world.product_id
    # A search hit whose page is missing is shown as not usable, never saved.
    assert by_domain["unrelated.example.test"]["outcome"] == "dropped"
    assert result["totals"]["sites_auto"] == 1
    assert [s["domain"] for s in block["sites"]] == [ALPHA_HOST]


def test_the_reporting_scope_covers_only_reporting_customers(committed_world: World) -> None:
    world = committed_world
    _web, getter, search, resolve = _fake_world()
    plan = _run(world, {"scope": "reporting"}, getter, resolve, search)
    assert [b["customer_id"] for b in plan["result"]["customers"]] == [world.alpha_id]


def test_a_missing_setting_makes_the_preview_refuse_and_the_unlinked_scope_run_anyway(committed_world: World) -> None:
    world = committed_world
    with SessionLocal() as session:
        session.execute(text("DELETE FROM tenant_setting WHERE tenant_id = :t"), {"t": world.tenant})
        session.commit()
    web, getter, search, resolve = _fake_world()
    refused = _run(world, {"scope": "customer", "customer_id": world.alpha_id}, getter, resolve, search)
    assert refused["status"] == "failed" and refused["error"] == "settings_missing" and refused["result"] is None
    unlinked = _run(world, {"scope": "unlinked_listings", "customer_id": None}, getter, resolve, search)
    assert unlinked["status"] == "done"
    assert web.calls == []  # nothing was fetched or searched for the refused scope
    assert search.queries == []


def test_a_write_inside_a_preview_is_rejected_by_the_database(committed_world: World, monkeypatch) -> None:
    world = committed_world
    _web, getter, search, resolve = _fake_world()
    with SessionLocal() as session:

        def evil_step(candidates, _getter, **_kwargs):
            session.add(
                CustomerWebSite(
                    tenant_id=world.tenant,
                    customer_id=world.alpha_id,
                    domain="evil.example.test",
                    status="proposed",
                    source="auto",
                    evidence={},
                )
            )
            session.flush()
            return candidates

        monkeypatch.setattr(cand, "load_homepages", evil_step)
        with pytest.raises(DBAPIError) as caught:
            preview.run_preview(
                session,
                tenant_id=world.tenant,
                preview_id=str(uuid.uuid4()),
                request={"scope": "customer", "customer_id": world.alpha_id},
                getter=getter,
                resolve=resolve,
                plan_store=preview.MemoryPlanStore(),
                search=search,
                engine_hosts=frozenset(),
            )
        session.rollback()
    original = caught.value.orig
    assert type(original).__name__ == "ReadOnlySqlTransaction" or "read-only" in str(caught.value).lower()
    assert _snapshot(world.tenant)["customer_web_site"][0] == 0
