"""Customer sign-off link against a real database. One rolled-back transaction; cip_test only."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from urllib.parse import parse_qs, urlparse

import pytest
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.sync_url import sqlalchemy_sync_engine_url
from app.models.cpor import CporCase, CporCaseEvent
from app.models.cpor_approval import CporCaseApprovalLink
from app.services.cpor import customer_approval as ca

NOW = datetime(2026, 10, 14, 9, 0, tzinfo=timezone.utc)


@pytest.fixture
def session(monkeypatch: pytest.MonkeyPatch):
    engine = create_engine(sqlalchemy_sync_engine_url(get_settings().database_url_sync))
    with engine.connect() as conn:
        if conn.execute(text("select current_database()")).scalar() != "cip_test":
            pytest.skip("cip_test only")
        if conn.execute(text("select to_regclass('cpor_case_approval_link')")).scalar() is None:
            pytest.skip("20261012_0035 is not applied")
        conn.rollback()
        outer = conn.begin()
        db = Session(bind=conn, join_transaction_mode="create_savepoint")
        monkeypatch.setattr(
            ca, "get_settings", lambda: SimpleNamespace(cip_public_web_origin="https://example.test")
        )
        try:
            yield db
        finally:
            db.close()
            outer.rollback()
    engine.dispose()


def _case(db: Session) -> CporCase:
    case = db.scalars(select(CporCase).order_by(CporCase.id)).first()
    if case is None:
        pytest.skip("cip_test has no case")
    return case


def _send(db: Session, case: CporCase, **over) -> str:
    sent: list[dict] = []
    ca.issue_link(
        db,
        case_id=case.id,
        recipient_email="Buyer@Example.com",
        actor="planner@example.com",
        tenant_id=case.tenant_id or "default",
        now=over.get("now", NOW),
        send=lambda **mail: sent.append(mail),
    )
    db.flush()
    assert len(sent) == 1 and sent[0]["to_addr"] == "buyer@example.com"
    url = next(word for word in sent[0]["text_body"].split() if word.startswith("https://"))
    return parse_qs(urlparse(url).query)["token"][0]


def test_link_opens_one_case_and_stores_only_the_hash(session):
    case = _case(session)
    token = _send(session, case)
    row = session.scalars(
        select(CporCaseApprovalLink).where(CporCaseApprovalLink.case_id == case.id)
    ).all()[-1]
    assert row.token_hash != token and len(row.token_hash) == 64
    assert row.expires_at == NOW + ca.LINK_TTL

    summary = ca.read_public(session, token, now=NOW)
    assert tuple(summary) == ca.PUBLIC_KEYS
    assert summary["case_code"] == case.case_code
    assert summary["export_version"] == int(case.export_version)

    with pytest.raises(PermissionError):
        ca.read_public(session, token + "x", now=NOW)


def test_other_tenant_cannot_send_read_status_or_revoke(session):
    case = _case(session)
    other = (case.tenant_id or "default") + "-other"
    with pytest.raises(LookupError):
        ca.issue_link(
            session, case_id=case.id, recipient_email="a@b.c", actor="x", tenant_id=other,
            now=NOW, send=lambda **_: None,
        )
    with pytest.raises(LookupError):
        ca.status_for_planner(session, case.id, other, now=NOW)
    with pytest.raises(LookupError):
        ca.revoke_open(session, case_id=case.id, actor="x", tenant_id=other, now=NOW)


def test_decision_is_a_case_event_and_is_written_once(session):
    case = _case(session)
    token = _send(session, case)
    when = NOW + timedelta(hours=1)
    ca.decide_public(
        session, raw_token=token, decision="approved", signer_name=" Ada Buyer ",
        comment="Agreed", now=when,
    )
    session.flush()
    event = session.scalars(
        select(CporCaseEvent)
        .where(CporCaseEvent.case_id == case.id, CporCaseEvent.event_type == "customer_settlement_signoff")
        .order_by(CporCaseEvent.id.desc())
    ).first()
    assert event.actor == "Ada Buyer"
    assert event.payload_json["decision"] == "approved"
    assert event.payload_json["export_version"] == int(case.export_version)
    assert event.payload_json["decided_at"] == when.isoformat()
    assert event.payload_json["comment"] == "Agreed"

    with pytest.raises(PermissionError):
        ca.decide_public(
            session, raw_token=token, decision="rejected", signer_name="Eve", comment="No", now=when,
        )
    with pytest.raises(PermissionError):
        ca.read_public(session, token, now=when)
    view = ca.status_for_planner(session, case.id, case.tenant_id or "default", now=when)
    assert view["state"] == "decided" and view["decision"] == "approved"


def test_revoked_expired_and_stale_links_open_nothing(session):
    case = _case(session)
    token = _send(session, case)
    ca.revoke_open(session, case_id=case.id, actor="planner@example.com", now=NOW)
    session.flush()
    with pytest.raises(PermissionError):
        ca.read_public(session, token, now=NOW)

    token = _send(session, case)
    with pytest.raises(PermissionError):
        ca.read_public(session, token, now=NOW + ca.LINK_TTL)

    token = _send(session, case)
    case.export_version = int(case.export_version) + 1
    session.flush()
    with pytest.raises(PermissionError):
        ca.read_public(session, token, now=NOW)


def test_a_new_link_retires_the_open_one(session):
    case = _case(session)
    first = _send(session, case)
    _send(session, case)
    with pytest.raises(PermissionError):
        ca.read_public(session, first, now=NOW)
