"""Discovery V2 API: roles, tenant isolation, the settings_missing payload, preview, apply, review queue.

cip_test only. The plan store is in memory, the worker dispatch is recorded (never sent), and the
steward audit is recorded, so nothing leaves the process. Rows are committed under a unique tenant
and removed afterwards. Fictional names, ``.test`` hosts.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.api.v1 import router as api_router
from app.api.v1.endpoints import listing_discovery as endpoint
from app.db.session_sync import SessionLocal
from app.main import app
from app.services import tenant_settings as ts
from app.services.listing_capture import discovery
from app.services.listing_capture.web_discovery import apply as web_apply
from app.services.listing_capture.web_discovery import preview, scoring
from app.services.listing_capture.web_discovery.homepage import parse_home
from app.services.listing_capture.web_discovery.settings import load_discovery_settings
from tests.web_discovery_db import ALPHA_HOST, ALPHA_NAME, World, committed_world  # noqa: F401
from tests.web_discovery_support import COUNTRY, ENDINGS, fixture_text

BASE = "/api/v1/listing-capture/discovery"
# Unmatched X-User-Id so stub auth forges the header role (a missing id resolves an admin).
STEWARD = {"X-User-Role": "steward", "X-User-Id": "wd-steward-probe"}
VIEWER = {"X-User-Role": "viewer", "X-User-Id": "wd-viewer-probe"}


@dataclass
class Env:
    client: TestClient
    world: World
    store: preview.MemoryPlanStore
    dispatched: list[tuple[str, str, dict[str, Any]]] = field(default_factory=list)
    audit: list[dict[str, Any]] = field(default_factory=list)
    tenant: str = ""


@pytest.fixture()
def env(committed_world: World, monkeypatch) -> Env:
    store = preview.MemoryPlanStore()
    built = Env(client=TestClient(app), world=committed_world, store=store, tenant=committed_world.tenant)
    monkeypatch.setattr(endpoint, "tenant_id_from_user", lambda _user: built.tenant)
    # The request-scoped ORM filter (tenant_scope) is bound from the router's own lookup. Point it at the
    # same test tenant, or every tenant-owned read (customer, sites, candidates) is filtered to "default".
    monkeypatch.setattr(api_router, "tenant_id_from_user", lambda _user: built.tenant)
    monkeypatch.setattr(endpoint, "get_plan_store", lambda: store)
    monkeypatch.setattr(endpoint, "dispatch_preview", lambda tenant, pid, request: built.dispatched.append((tenant, pid, request)))
    monkeypatch.setattr(endpoint, "listing_live_fetch_enabled", lambda: True)
    monkeypatch.setattr(web_apply, "record_steward_audit_sync", lambda user, **kw: built.audit.append(kw))
    return built


def _drop_setting(tenant: str, key: str) -> None:
    with SessionLocal() as session:
        session.execute(text("DELETE FROM tenant_setting WHERE tenant_id = :t AND key = :k"), {"t": tenant, "k": key})
        session.commit()


def _auto_plan(env: Env, preview_id: str, *, host: str = ALPHA_HOST, queue_host: str = "other.example.test") -> str:
    """A finished preview in the store: one automatic site and one for review."""
    entries = []
    for item_id, entry_host, outcome, hits in (
        ("c-1", host, "auto_accept", [{"product_id": env.world.product_id, "product_label": "Widget One", "query": "q", "rank": 1}]),
        ("c-2", queue_host, "steward_queue", []),
    ):
        evidence = scoring.build_evidence(
            host=entry_host,
            customer_name=ALPHA_NAME,
            sources={scoring.SOURCE_GUESS},
            endings=ENDINGS,
            country=COUNTRY,
            home=parse_home(fixture_text("home_org_jsonld.html")),
            http_status=200,
            final_url=f"https://{entry_host}/",
            robots="allowed",
            product_hits=hits,
        )
        entries.append(
            {"item_id": item_id, "domain": entry_host, "outcome": outcome, "drop_reason": None, "proposed_site_key": None, "evidence": evidence}
        )
    plan = preview.new_plan(env.tenant, preview_id, {"scope": "reporting"})
    with SessionLocal() as session:
        fingerprint = load_discovery_settings(session, env.tenant).fingerprint()
        session.rollback()
    plan.update(
        status="done",
        settings_fingerprint=fingerprint,
        result={
            "scope": "reporting",
            "customers": [
                {
                    "customer_id": env.world.alpha_id,
                    "customer_name": ALPHA_NAME,
                    "reporting": True,
                    "notes": [],
                    "candidates": entries,
                    "sites": [],
                }
            ],
            "listings": [],
            "totals": {},
        },
    )
    env.store.save(env.tenant, preview_id, plan)
    return preview_id


# --------------------------------------------------------------------------- capabilities and roles


def test_capabilities_report_the_server_and_what_the_tenant_has_not_set(env: Env) -> None:
    body = env.client.get(f"{BASE}/capabilities", headers=VIEWER).json()
    assert body["live_fetch"] is True and isinstance(body["browser_available"], bool)
    assert [p["id"] for p in body["providers"]] == ["ddg_html", "ddg_lite", "searxng"]
    assert [p["id"] for p in body["providers"] if p["needs_url"]] == ["searxng"]
    assert body["settings"] == {"missing": []}

    env.tenant = f"wd-empty-{uuid.uuid4().hex[:8]}"  # a tenant that has set nothing
    empty = env.client.get(f"{BASE}/capabilities", headers=VIEWER).json()
    assert empty["settings"]["missing"] == [ts.KEY_TENANT_COUNTRY, ts.KEY_TENANT_DOMAIN_ENDINGS]


def test_writes_need_the_steward_role_and_reads_do_not(env: Env) -> None:
    client = env.client
    assert client.post(f"{BASE}/previews", json={"scope": "reporting"}, headers=VIEWER).status_code == 403
    assert client.post(f"{BASE}/previews/{uuid.uuid4()}/apply", headers=VIEWER).status_code == 403
    assert client.post(f"{BASE}/site-candidates/1", json={"action": "confirm"}, headers=VIEWER).status_code == 403
    assert client.get(f"{BASE}/site-candidates", headers=VIEWER).status_code == 200
    assert client.get(f"{BASE}/previews/{uuid.uuid4()}", headers=VIEWER).status_code == 200
    assert env.dispatched == []


# --------------------------------------------------------------------------- starting a preview


def test_settings_missing_payload_names_the_keys(env: Env) -> None:
    env.tenant = f"wd-empty-{uuid.uuid4().hex[:8]}"
    response = env.client.post(f"{BASE}/previews", json={"scope": "reporting"}, headers=STEWARD)
    assert response.status_code == 409
    body = response.json()
    assert body["code"] == "settings_missing"
    assert body["missing"] == [ts.KEY_TENANT_COUNTRY, ts.KEY_TENANT_DOMAIN_ENDINGS]
    assert "Settings" in body["message"]
    assert env.dispatched == [] and env.store.plans == {}
    # The unlinked-listings scope needs no settings.
    assert env.client.post(f"{BASE}/previews", json={"scope": "unlinked_listings"}, headers=STEWARD).status_code == 202


def test_the_domain_scope_needs_only_the_country(env: Env) -> None:
    _drop_setting(env.tenant, ts.KEY_TENANT_DOMAIN_ENDINGS)
    body = {"scope": "domain", "customer_id": env.world.alpha_id, "domain": "Typed.Example.Test"}
    assert env.client.post(f"{BASE}/previews", json=body, headers=STEWARD).status_code == 202
    assert env.dispatched[0][2] == {"scope": "domain", "customer_id": env.world.alpha_id, "domain": "typed.example.test"}
    env.store.release(env.tenant, env.dispatched[0][1])
    _drop_setting(env.tenant, ts.KEY_TENANT_COUNTRY)
    refused = env.client.post(f"{BASE}/previews", json=body, headers=STEWARD)
    assert refused.status_code == 409 and refused.json()["missing"] == [ts.KEY_TENANT_COUNTRY]
    assert env.client.post(f"{BASE}/previews", json={"scope": "customer", "customer_id": env.world.alpha_id}, headers=STEWARD).json()["missing"] == [
        ts.KEY_TENANT_COUNTRY,
        ts.KEY_TENANT_DOMAIN_ENDINGS,
    ]


def test_a_preview_is_queued_once_per_tenant_at_a_time(env: Env) -> None:
    response = env.client.post(f"{BASE}/previews", json={"scope": "customer", "customer_id": env.world.alpha_id}, headers=STEWARD)
    assert response.status_code == 202
    first = response.json()
    assert first["status"] == "queued" and uuid.UUID(first["preview_id"])
    assert env.dispatched == [(env.tenant, first["preview_id"], {"scope": "customer", "customer_id": env.world.alpha_id})]
    assert env.store.load(env.tenant, first["preview_id"])["status"] == "queued"

    busy = env.client.post(f"{BASE}/previews", json={"scope": "reporting"}, headers=STEWARD)
    assert busy.status_code == 409 and busy.json()["code"] == "preview_running"
    assert busy.json()["preview_id"] == first["preview_id"]
    assert len(env.dispatched) == 1

    polled = env.client.get(f"{BASE}/previews/{first['preview_id']}", headers=VIEWER).json()
    assert polled["status"] == "queued" and polled["progress"] == {"done": 0, "total": 0}
    assert polled["result"] is None and polled["applied"] is None

    env.store.release(env.tenant, first["preview_id"])
    assert env.client.post(f"{BASE}/previews", json={"scope": "reporting"}, headers=STEWARD).status_code == 202


def test_request_validation(env: Env) -> None:
    post = lambda body: env.client.post(f"{BASE}/previews", json=body, headers=STEWARD)  # noqa: E731
    assert (post({"scope": "nope"}).status_code, post({"scope": "nope"}).json()["code"]) == (422, "scope_invalid")
    assert post({"scope": "customer"}).json()["code"] == "customer_required"
    bad_domain = post({"scope": "domain", "customer_id": env.world.alpha_id, "domain": "https://x.example.test/path"})
    assert bad_domain.status_code == 422 and bad_domain.json()["code"] == "domain_invalid"
    missing_customer = post({"scope": "customer", "customer_id": 2_000_000_000})
    assert missing_customer.status_code == 422 and missing_customer.json()["code"] == "customer_not_found"
    assert env.dispatched == []


def test_a_customer_of_another_tenant_is_not_found(env: Env) -> None:
    other_world_customer = env.world.alpha_id
    env.tenant = f"wd-other-{uuid.uuid4().hex[:8]}"
    response = env.client.post(f"{BASE}/previews", json={"scope": "customer", "customer_id": other_world_customer}, headers=STEWARD)
    assert response.status_code == 422 and response.json()["code"] == "customer_not_found"


def test_live_fetch_off_refuses_before_anything_is_queued(env: Env, monkeypatch) -> None:
    monkeypatch.setattr(endpoint, "listing_live_fetch_enabled", lambda: False)
    response = env.client.post(f"{BASE}/previews", json={"scope": "reporting"}, headers=STEWARD)
    assert response.status_code == 409 and response.json()["code"] == "live_fetch_off"
    assert env.dispatched == [] and env.store.plans == {} and env.store.locks == {}
    assert env.client.get(f"{BASE}/capabilities", headers=VIEWER).json()["live_fetch"] is False


def test_an_unreachable_store_or_broker_answers_503_and_frees_the_lock(env: Env, monkeypatch) -> None:
    def down():
        raise preview.StoreUnavailable("ConnectionError")

    monkeypatch.setattr(endpoint, "get_plan_store", down)
    unavailable = env.client.post(f"{BASE}/previews", json={"scope": "reporting"}, headers=STEWARD)
    assert unavailable.status_code == 503 and unavailable.json()["code"] == "store_unavailable"
    assert env.client.get(f"{BASE}/previews/{uuid.uuid4()}", headers=VIEWER).status_code == 503
    assert env.client.post(f"{BASE}/previews/{uuid.uuid4()}/apply", headers=STEWARD).status_code == 503

    monkeypatch.setattr(endpoint, "get_plan_store", lambda: env.store)

    def broken(*_args):
        raise RuntimeError("broker down")

    monkeypatch.setattr(endpoint, "dispatch_preview", broken)
    failed = env.client.post(f"{BASE}/previews", json={"scope": "reporting"}, headers=STEWARD)
    assert failed.status_code == 503 and failed.json()["code"] == "dispatch_failed"
    assert env.store.locks == {}


def test_a_preview_of_another_tenant_reads_as_expired(env: Env) -> None:
    pid = _auto_plan(env, str(uuid.uuid4()))
    assert env.client.get(f"{BASE}/previews/{pid}", headers=VIEWER).json()["status"] == "done"
    env.tenant = f"wd-other-{uuid.uuid4().hex[:8]}"
    other = env.client.get(f"{BASE}/previews/{pid}", headers=VIEWER).json()
    assert other["status"] == "expired" and other["result"] is None
    applied = env.client.post(f"{BASE}/previews/{pid}/apply", headers=STEWARD)
    assert applied.status_code == 410 and applied.json()["code"] == "preview_expired"


# --------------------------------------------------------------------------- apply and the review queue


def test_apply_saves_what_the_preview_showed_and_a_second_apply_changes_nothing(env: Env) -> None:
    pid = _auto_plan(env, str(uuid.uuid4()))
    first = env.client.post(f"{BASE}/previews/{pid}/apply", headers=STEWARD)
    assert first.status_code == 200, first.text
    body = first.json()
    assert (body["sites_confirmed"], body["sites_queued"], body["sites_created"], body["skipped"]) == (1, 1, 1, [])
    assert env.audit[-1]["action"] == "discovery_apply"

    second = env.client.post(f"{BASE}/previews/{pid}/apply", headers=STEWARD)
    assert second.status_code == 200 and second.json() == body
    assert len(env.audit) == 1  # nothing was written the second time
    polled = env.client.get(f"{BASE}/previews/{pid}", headers=VIEWER).json()
    assert polled["applied"] == body

    with SessionLocal() as session:
        rows = session.execute(
            text("SELECT domain, status FROM customer_web_site WHERE tenant_id = :t ORDER BY domain"), {"t": env.tenant}
        ).all()
        sites = session.scalar(text("SELECT count(*) FROM listing_site WHERE tenant_id = :t"), {"t": env.tenant})
        session.rollback()
    assert [tuple(r) for r in rows] == [(ALPHA_HOST, "confirmed"), ("other.example.test", "proposed")]
    assert sites == 1


def test_changed_settings_and_unfinished_previews_are_refused(env: Env) -> None:
    pid = _auto_plan(env, str(uuid.uuid4()))
    _drop_setting(env.tenant, ts.KEY_DISCOVERY_SEARCH_PROVIDERS)
    changed = env.client.post(f"{BASE}/previews/{pid}/apply", headers=STEWARD)
    assert changed.status_code == 409 and changed.json()["code"] == "settings_changed"

    running = str(uuid.uuid4())
    plan = preview.new_plan(env.tenant, running, {"scope": "reporting"})
    plan["status"] = "running"
    env.store.save(env.tenant, running, plan)
    unfinished = env.client.post(f"{BASE}/previews/{running}/apply", headers=STEWARD)
    assert unfinished.status_code == 409 and unfinished.json()["code"] == "preview_not_done"
    with SessionLocal() as session:
        assert session.scalar(text("SELECT count(*) FROM customer_web_site WHERE tenant_id = :t"), {"t": env.tenant}) == 0
        session.rollback()


def test_the_review_queue_lists_confirms_and_rejects(env: Env) -> None:
    pid = _auto_plan(env, str(uuid.uuid4()))
    assert env.client.post(f"{BASE}/previews/{pid}/apply", headers=STEWARD).status_code == 200

    items = env.client.get(f"{BASE}/site-candidates?status=proposed", headers=VIEWER).json()["items"]
    mine = [i for i in items if i["domain"] == "other.example.test"]
    assert len(mine) == 1 and mine[0]["customer_name"] == ALPHA_NAME and mine[0]["customer_id"] == env.world.alpha_id
    assert "name_match" in mine[0]["evidence"]
    assert env.client.get(f"{BASE}/site-candidates?status=bogus", headers=VIEWER).status_code == 422

    candidate_id = mine[0]["id"]
    confirmed = env.client.post(f"{BASE}/site-candidates/{candidate_id}", json={"action": "confirm"}, headers=STEWARD)
    assert confirmed.status_code == 200 and confirmed.json() == {"id": candidate_id, "status": "confirmed", "site_created": True}
    again = env.client.post(f"{BASE}/site-candidates/{candidate_id}", json={"action": "confirm"}, headers=STEWARD)
    assert again.status_code == 409 and again.json()["code"] == "not_proposed"
    assert env.client.get(f"{BASE}/site-candidates", headers=VIEWER).json()["items"] == []
    rejected = env.client.post(f"{BASE}/site-candidates/{candidate_id}", json={"action": "reject"}, headers=STEWARD)
    assert rejected.status_code == 200 and rejected.json()["status"] == "rejected"
    listed = env.client.get(f"{BASE}/site-candidates?status=rejected", headers=VIEWER).json()["items"]
    assert [i["id"] for i in listed] == [candidate_id]
    assert [c["action"] for c in env.audit if c["action"].startswith("site_candidate")] == [
        "site_candidate_confirm",
        "site_candidate_reject",
    ]


def test_the_review_queue_is_tenant_scoped(env: Env) -> None:
    pid = _auto_plan(env, str(uuid.uuid4()))
    assert env.client.post(f"{BASE}/previews/{pid}/apply", headers=STEWARD).status_code == 200
    candidate_id = next(
        i["id"] for i in env.client.get(f"{BASE}/site-candidates", headers=VIEWER).json()["items"] if i["domain"] == "other.example.test"
    )
    env.tenant = f"wd-other-{uuid.uuid4().hex[:8]}"
    assert env.client.get(f"{BASE}/site-candidates", headers=VIEWER).json() == {"items": []}
    hidden = env.client.post(f"{BASE}/site-candidates/{candidate_id}", json={"action": "confirm"}, headers=STEWARD)
    assert hidden.status_code == 404 and hidden.json()["code"] == "not_found"
    assert env.client.post(f"{BASE}/site-candidates/{candidate_id}", json={"action": "nope"}, headers=STEWARD).status_code == 404
    env.tenant = env.world.tenant
    assert env.client.post(f"{BASE}/site-candidates/{candidate_id}", json={"action": "nope"}, headers=STEWARD).status_code == 422


def test_a_confirmed_site_is_read_by_discovery_after_apply(env: Env) -> None:
    pid = _auto_plan(env, str(uuid.uuid4()))
    assert env.client.post(f"{BASE}/previews/{pid}/apply", headers=STEWARD).status_code == 200
    with SessionLocal() as session:
        keys = discovery._site_keys(session, tenant_id=env.tenant, customer_id=env.world.alpha_id, seed={})
        session.rollback()
    assert discovery._site_key_from_origin(f"https://{ALPHA_HOST}") in keys
