"""N-0100: public GET and POST /api/v1/case-approval are throttled per client and per token.

The route stays public. A miss under the limit is the same 404 body. One open and one
decision succeed. The next call is 429. cip_test only; nothing here targets cip.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

import pytest
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, delete, select, text

from app.core import case_approval_throttle as throttle_mod
from app.core.config import get_settings
from app.core.password import hash_session_token, new_session_token
from app.db.session_sync import SessionLocal
from app.db.sync_url import sqlalchemy_sync_engine_url
from app.main import app
from app.models.cpor import CporCase, CporCaseEvent
from app.models.cpor_approval import CporCaseApprovalLink
from app.services.cpor.customer_approval import LINK_TTL, PUBLIC_MISS

PATH = "/api/v1/case-approval"
MISS = {"detail": PUBLIC_MISS}
TOO_MANY = {"detail": "Too many requests. Try again later."}
SIGNER = "N0100 Buyer"


class _Clock:
    def __init__(self) -> None:
        self.t = 10_000.0

    def __call__(self) -> float:
        return self.t


def _require_cip_test() -> None:
    engine = create_engine(sqlalchemy_sync_engine_url(get_settings().database_url_sync))
    try:
        with engine.connect() as conn:
            name = conn.execute(text("select current_database()")).scalar()
    finally:
        engine.dispose()
    if name != "cip_test":
        pytest.skip("cip_test only")


@pytest.fixture(autouse=True)
def clock(monkeypatch: pytest.MonkeyPatch) -> _Clock:
    c = _Clock()
    limiter = throttle_mod.case_approval_throttle
    limiter.reset_all()
    limiter.window_seconds = throttle_mod.WINDOW_SECONDS
    limiter.max_per_token = throttle_mod.MAX_PER_TOKEN
    limiter.max_per_client = throttle_mod.MAX_PER_CLIENT
    monkeypatch.setattr(limiter, "_clock", c)
    yield c
    limiter.reset_all()
    limiter.window_seconds = throttle_mod.WINDOW_SECONDS
    limiter.max_per_token = throttle_mod.MAX_PER_TOKEN
    limiter.max_per_client = throttle_mod.MAX_PER_CLIENT


@pytest.fixture
def client():
    _require_cip_test()
    with TestClient(app) as http:
        yield http


def _bad(n: int) -> str:
    return f"n0100-missing-token-{n:04d}-xxxxxxxx"


def test_defaults_allow_one_open_and_one_decision() -> None:
    assert throttle_mod.MAX_PER_TOKEN >= 2
    assert throttle_mod.MAX_PER_CLIENT >= 2
    assert throttle_mod.WINDOW_SECONDS >= 1


def test_public_route_still_has_no_user_and_no_role() -> None:
    public = [
        r
        for r in app.routes
        if isinstance(r, APIRoute) and r.path == PATH
    ]
    assert public
    for route in public:
        names = []
        stack = [route.dependant]
        while stack:
            dep = stack.pop()
            call = getattr(dep, "call", None)
            if call is not None:
                names.append(getattr(call, "__name__", ""))
            stack.extend(getattr(dep, "dependencies", None) or [])
        assert "get_current_user" not in names
        assert "require_roles" not in names


def test_bad_token_stays_404_with_the_same_miss_body(client: TestClient) -> None:
    token = _bad(1)
    got = client.get(PATH, params={"token": token})
    posted = client.post(
        PATH,
        json={
            "token": token,
            "decision": "rejected",
            "signer_name": SIGNER,
            "comment": "No such link",
        },
    )
    assert got.status_code == 404
    assert posted.status_code == 404
    assert got.json() == MISS
    assert posted.json() == MISS


def test_same_token_over_the_limit_is_429_and_another_token_is_still_404(
    client: TestClient,
) -> None:
    limiter = throttle_mod.case_approval_throttle
    limiter.max_per_token = 2
    limiter.max_per_client = 50
    token = _bad(2)
    assert client.get(PATH, params={"token": token}).json() == MISS
    assert client.get(PATH, params={"token": token}).json() == MISS
    blocked = client.get(PATH, params={"token": token})
    assert blocked.status_code == 429
    assert blocked.json() == TOO_MANY
    assert blocked.headers["retry-after"].isdigit()
    other = client.get(PATH, params={"token": _bad(3)})
    assert other.status_code == 404
    assert other.json() == MISS


def test_client_over_the_limit_is_429_across_tokens(client: TestClient) -> None:
    limiter = throttle_mod.case_approval_throttle
    limiter.max_per_token = 50
    limiter.max_per_client = 2
    assert client.get(PATH, params={"token": _bad(4)}).status_code == 404
    assert client.post(
        PATH,
        json={
            "token": _bad(5),
            "decision": "approved",
            "signer_name": SIGNER,
            "comment": "Still a miss",
        },
    ).status_code == 404
    blocked = client.get(PATH, params={"token": _bad(6)})
    assert blocked.status_code == 429
    assert blocked.json() == TOO_MANY
    assert blocked.json() != MISS


def test_window_expiry_allows_the_token_again(client: TestClient, clock: _Clock) -> None:
    limiter = throttle_mod.case_approval_throttle
    limiter.max_per_token = 1
    limiter.max_per_client = 50
    token = _bad(7)
    assert client.get(PATH, params={"token": token}).status_code == 404
    blocked = client.get(PATH, params={"token": token})
    assert blocked.status_code == 429
    assert blocked.headers["retry-after"] == str(throttle_mod.WINDOW_SECONDS)
    clock.t += throttle_mod.WINDOW_SECONDS
    again = client.get(PATH, params={"token": token})
    assert again.status_code == 404
    assert again.json() == MISS


def test_throttle_log_does_not_contain_the_raw_token(
    client: TestClient, caplog: pytest.LogCaptureFixture
) -> None:
    token = "n0100-raw-token-must-not-be-logged-xxxx"
    throttle_mod.case_approval_throttle.max_per_token = 1
    caplog.set_level(logging.WARNING, logger="app.core.case_approval_throttle")
    client.get(PATH, params={"token": token})
    blocked = client.get(PATH, params={"token": token})
    assert blocked.status_code == 429
    assert token not in caplog.text


def test_one_open_and_one_decision_succeed_and_the_next_call_is_429(client: TestClient) -> None:
    _require_cip_test()
    raw = new_session_token()
    link_id = None
    case_id = None
    with SessionLocal() as session:
        case = session.scalars(select(CporCase).order_by(CporCase.id)).first()
        if case is None:
            pytest.skip("cip_test has no case")
        row = CporCaseApprovalLink(
            case_id=case.id,
            token_hash=hash_session_token(raw),
            export_version=int(case.export_version),
            recipient_email="n0100-buyer@example.com",
            expires_at=datetime.now(timezone.utc) + LINK_TTL,
            created_by="n0100-throttle-test",
        )
        session.add(row)
        session.commit()
        link_id = int(row.id)
        case_id = int(case.id)
    limiter = throttle_mod.case_approval_throttle
    limiter.reset_all()
    limiter.max_per_token = 2
    limiter.max_per_client = 50
    try:
        opened = client.get(PATH, params={"token": raw})
        assert opened.status_code == 200, opened.text
        assert opened.json()["case_code"]
        decided = client.post(
            PATH,
            json={
                "token": raw,
                "decision": "approved",
                "signer_name": SIGNER,
                "comment": "Agreed under the limit",
            },
        )
        assert decided.status_code == 200, decided.text
        assert decided.json() == {"ok": True}
        excess = client.get(PATH, params={"token": raw})
        assert excess.status_code == 429
        assert excess.json() == TOO_MANY
    finally:
        with SessionLocal() as session:
            session.execute(
                delete(CporCaseEvent).where(
                    CporCaseEvent.case_id == case_id,
                    CporCaseEvent.event_type == "customer_settlement_signoff",
                    CporCaseEvent.actor == SIGNER,
                )
            )
            session.execute(delete(CporCaseApprovalLink).where(CporCaseApprovalLink.id == link_id))
            session.commit()
