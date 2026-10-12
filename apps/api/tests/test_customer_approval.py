"""Customer sign-off link rules. No database and no mailed token."""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from app.services.cpor.customer_approval import (
    PUBLIC_KEYS,
    compose_approval_mail,
    link_block,
    planner_view,
    public_summary,
    signoff_event,
)


def _link(**over):
    now = datetime(2026, 10, 12, tzinfo=timezone.utc)
    base = dict(
        revoked_at=None,
        decided_at=None,
        expires_at=now + timedelta(days=7),
        export_version=3,
        recipient_email="buyer@example.com",
        decision=None,
        signer_name=None,
    )
    base.update(over)
    return SimpleNamespace(**base), now


def test_open_link_has_no_block():
    link, now = _link()
    assert link_block(link, now=now, current_version=3) is None


def test_expired_revoked_decided_and_stale_are_blocked():
    now = datetime(2026, 10, 12, tzinfo=timezone.utc)
    expired, _ = _link(expires_at=now - timedelta(seconds=1))
    revoked, _ = _link(revoked_at=now)
    decided, _ = _link(decided_at=now, decision="approved")
    stale, _ = _link(export_version=2)
    assert link_block(expired, now=now, current_version=3) == "expired"
    assert link_block(revoked, now=now, current_version=3) == "revoked"
    assert link_block(decided, now=now, current_version=3) == "decided"
    assert link_block(stale, now=now, current_version=3) == "stale"
    assert link_block(None, now=now, current_version=3) == "missing"


def test_public_summary_is_only_this_case():
    summary = public_summary(
        {
            "case_id": 99,
            "window_start": "2026-04-01",
            "window_end": "2026-04-30",
            "ledger": {"paid": 10},
            "desk": {"customer_amount": 1200.5, "cip_amount": 999},
            "lines": [
                {
                    "line_id": 7,
                    "product_id": 4,
                    "product_name": "Widget",
                    "estimate_qty": 10,
                    "result_qty": 8,
                    "support_unit": 5,
                    "ttl_result": 40,
                }
            ],
        },
        case_code="C1",
        case_name="April",
        customer_name="Takealot",
        currency="ZAR",
        export_version=3,
    )
    assert tuple(summary) == PUBLIC_KEYS
    assert summary["lines"] == [
        {
            "product": "Widget",
            "estimate_qty": 10,
            "result_qty": 8,
            "support_per_unit": 5,
            "support_total": 40,
        }
    ]
    assert summary["support_total"] == 1200.5
    assert "case_id" not in summary
    assert "ledger" not in summary


def test_signoff_records_who_when_and_version():
    when = datetime(2026, 10, 12, 12, 0, tzinfo=timezone.utc)
    event = signoff_event(
        decision="approved",
        signer_name="Ada Buyer",
        comment="Agreed",
        export_version=3,
        recipient_email="buyer@example.com",
        decided_at=when,
    )
    assert event["event_type"] == "customer_settlement_signoff"
    assert event["actor"] == "Ada Buyer"
    assert event["payload"]["export_version"] == 3
    assert event["payload"]["decided_at"] == when.isoformat()
    assert event["payload"]["comment"] == "Agreed"


def test_mail_names_one_case_and_the_link():
    subject, text, html = compose_approval_mail("https://example.test/case-approval?token=abc", "C24")
    assert "C24" in subject
    assert "https://example.test/case-approval?token=abc" in text
    assert "C24" in html
    assert "token=abc" in html


def test_planner_view_hides_the_token():
    link, now = _link()
    view = planner_view(link, now=now, current_version=3)
    assert view["state"] == "open"
    assert "token" not in view
    assert view["recipient_email"] == "buyer@example.com"
