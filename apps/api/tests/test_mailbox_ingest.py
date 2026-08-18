"""Mailbox ingest Unit 1 — poller gating, allowlist, RFC822 attachments (no live IMAP)."""

from __future__ import annotations

from datetime import datetime, timezone
from email.mime.application import MIMEApplication
from email.mime.message import MIMEMessage
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from unittest.mock import MagicMock, patch

from app.services.mailbox_ingest.config import (
    mailbox_allowed_senders,
    mailbox_env_disabled_reason,
    mailbox_ingest_enabled,
    mailbox_ingest_poll_interval_seconds,
    mailbox_transport,
)
from app.services.mailbox_ingest.graph_fetch import attachments_from_graph_message
from app.services.mailbox_ingest.imap_fetch import (
    ImapBasicAuthDisabled,
    attachments_from_rfc822,
    filename_is_shipment_workbook,
    imap_allowlist_since_criteria,
    imap_since_date,
    imap_unseen_allowlist_criteria,
    normalize_email_addr,
    normalize_message_id,
    sender_is_allowlisted,
)
from app.services.mailbox_ingest_runner import run_mailbox_ingest_once, spawn_mailbox_ingest_poller


def test_mailbox_ingest_disabled_under_pytest(monkeypatch):
    monkeypatch.setenv("CIP_MAILBOX_INGEST_ENABLED", "1")
    monkeypatch.setenv("CIP_MAILBOX_IMAP_USER", "warren_eliason@asus.com")
    monkeypatch.setenv("CIP_MAILBOX_IMAP_PASSWORD", "secret")
    monkeypatch.setenv("CIP_MAILBOX_SHIPMENT_SOURCE_ID", "6")
    monkeypatch.setenv("CIP_MAILBOX_ALLOWED_SENDERS", "Jess_Mah@asus.com")
    assert mailbox_ingest_enabled() is False
    assert mailbox_env_disabled_reason() == "pytest"


def test_mailbox_ingest_enabled_outside_pytest(monkeypatch):
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    monkeypatch.setenv("CIP_MAILBOX_INGEST_ENABLED", "1")
    monkeypatch.setenv("CIP_MAILBOX_IMAP_USER", "warren_eliason@asus.com")
    monkeypatch.setenv("CIP_MAILBOX_IMAP_PASSWORD", "secret")
    monkeypatch.setenv("CIP_MAILBOX_SHIPMENT_SOURCE_ID", "6")
    monkeypatch.setenv("CIP_MAILBOX_ALLOWED_SENDERS", "Jess_Mah@asus.com, warren_eliason@asus.com")
    assert mailbox_ingest_enabled() is True
    assert "jess_mah@asus.com" in mailbox_allowed_senders()
    assert "warren_eliason@asus.com" in mailbox_allowed_senders()
    monkeypatch.setenv("CIP_MAILBOX_INGEST_ENABLED", "0")
    assert mailbox_ingest_enabled() is False


def test_graph_enabled_without_imap_password(monkeypatch):
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    monkeypatch.setenv("CIP_MAILBOX_INGEST_ENABLED", "1")
    monkeypatch.setenv("CIP_MAILBOX_TRANSPORT", "graph")
    monkeypatch.setenv("CIP_MAILBOX_GRAPH_CLIENT_ID", "00000000-0000-0000-0000-000000000000")
    monkeypatch.setenv("CIP_MAILBOX_IMAP_USER", "warren_eliason@asus.com")
    monkeypatch.setenv("CIP_MAILBOX_IMAP_PASSWORD", "")
    monkeypatch.setenv("CIP_MAILBOX_SHIPMENT_SOURCE_ID", "6")
    monkeypatch.setenv("CIP_MAILBOX_ALLOWED_SENDERS", "Jess_Mah@asus.com")
    assert mailbox_transport() == "graph"
    assert mailbox_ingest_enabled() is True


def test_graph_parses_xlsx_and_skips_non_allowlisted():
    import base64

    payload = b"PK\x03\x04fake-xlsx"
    message = {
        "id": "g1",
        "internetMessageId": "<mid-g@asus.com>",
        "from": {"emailAddress": {"address": "Jess_Mah@asus.com"}},
        "subject": "Shipping report",
        "receivedDateTime": "2026-08-18T08:00:00Z",
    }
    atts = [
        {
            "@odata.type": "#microsoft.graph.fileAttachment",
            "name": "ACZA.xlsx",
            "contentBytes": base64.b64encode(payload).decode("ascii"),
        }
    ]
    allowed = frozenset({"jess_mah@asus.com"})
    parts = attachments_from_graph_message(message, atts, allowed_senders=allowed)
    assert len(parts) == 1
    assert parts[0].payload == payload
    assert parts[0].uid == "g1"
    assert parts[0].message_id == "mid-g@asus.com"
    skipped = attachments_from_graph_message(
        {**message, "from": {"emailAddress": {"address": "other@asus.com"}}},
        atts,
        allowed_senders=allowed,
    )
    assert skipped == []


def test_poll_interval_clamped(monkeypatch):
    monkeypatch.setenv("CIP_MAILBOX_POLL_SECONDS", "5")
    assert mailbox_ingest_poll_interval_seconds() == 15
    monkeypatch.setenv("CIP_MAILBOX_POLL_SECONDS", "99999")
    assert mailbox_ingest_poll_interval_seconds() == 3600


def test_sender_allowlist_and_filename():
    allowed = frozenset({"jess_mah@asus.com", "warren_eliason@asus.com"})
    assert sender_is_allowlisted("Jess Mah(Wai Ling Mah) <Jess_Mah@asus.com>", allowed)
    assert sender_is_allowlisted("warren_eliason@asus.com", allowed)
    assert not sender_is_allowlisted("other@asus.com", allowed)
    assert filename_is_shipment_workbook("ACZA.xlsx")
    assert filename_is_shipment_workbook("report.XLSM")
    assert filename_is_shipment_workbook("x.csv")
    assert not filename_is_shipment_workbook("notes.pdf")
    assert not filename_is_shipment_workbook("old.xls")
    assert normalize_email_addr("Jess Mah <Jess_Mah@asus.com>") == "jess_mah@asus.com"
    assert normalize_message_id("<abc@asus.com>") == "abc@asus.com"


def test_imap_allowlist_search_nests_or():
    one = imap_unseen_allowlist_criteria(frozenset({"jess_mah@asus.com"}))
    assert one == ("UNSEEN", "FROM", "jess_mah@asus.com")
    two = imap_unseen_allowlist_criteria(
        frozenset({"jess_mah@asus.com", "warren.eliason@gmail.com"})
    )
    assert two[0] == "UNSEEN"
    assert two.count("OR") == 1
    since = imap_since_date(days=3, now=datetime(2026, 8, 18, tzinfo=timezone.utc))
    assert since == "15-Aug-2026"
    crit = imap_allowlist_since_criteria(frozenset({"jess_mah@asus.com"}), since=since)
    assert crit == ("SINCE", "15-Aug-2026", "FROM", "jess_mah@asus.com")


def _xlsx_rfc822(*, sender: str, filename: str, body: bytes, message_id: str) -> bytes:
    outer = MIMEMultipart()
    outer["From"] = sender
    outer["Subject"] = "Shipping report"
    outer["Message-ID"] = f"<{message_id}>"
    outer.attach(MIMEText("see attached"))
    part = MIMEApplication(body, Name=filename)
    part.add_header("Content-Disposition", "attachment", filename=filename)
    outer.attach(part)
    return outer.as_bytes()


def test_attachments_from_rfc822_extracts_xlsx_only():
    raw = _xlsx_rfc822(
        sender="Jess Mah <Jess_Mah@asus.com>",
        filename="Shipped.xlsx",
        body=b"PK\x03\x04fake-xlsx",
        message_id="mid-1@asus.com",
    )
    parts = attachments_from_rfc822(raw)
    assert len(parts) == 1
    assert parts[0].filename == "Shipped.xlsx"
    assert parts[0].from_addr == "jess_mah@asus.com"
    assert parts[0].message_id == "mid-1@asus.com"
    assert parts[0].checksum_sha256


def test_attachments_from_forwarded_rfc822_wrapper():
    inner = email_message_xlsx()
    outer = MIMEMultipart()
    outer["From"] = "warren.eliason@gmail.com"
    outer["Subject"] = "Fwd: Shipping report"
    outer["Message-ID"] = "<fwd-1@gmail.com>"
    outer.attach(MIMEText("forwarded"))
    outer.attach(MIMEMessage(inner))
    parts = attachments_from_rfc822(outer.as_bytes())
    assert len(parts) == 1
    assert parts[0].filename == "Shipped.xlsx"
    assert parts[0].from_addr == "warren.eliason@gmail.com"


def email_message_xlsx():
    from email import message_from_bytes

    return message_from_bytes(
        _xlsx_rfc822(
            sender="Jess Mah <Jess_Mah@asus.com>",
            filename="Shipped.xlsx",
            body=b"PK\x03\x04fake-xlsx",
            message_id="inner@asus.com",
        )
    )


def test_run_once_skipped_when_disabled():
    out = run_mailbox_ingest_once(fetch=lambda: [])
    assert out["skipped"] is True
    assert out["reason"] == "pytest"


def test_run_once_ingests_and_marks_seen(monkeypatch):
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    monkeypatch.setenv("CIP_MAILBOX_INGEST_ENABLED", "1")
    monkeypatch.setenv("CIP_MAILBOX_IMAP_USER", "warren_eliason@asus.com")
    monkeypatch.setenv("CIP_MAILBOX_IMAP_PASSWORD", "secret")
    monkeypatch.setenv("CIP_MAILBOX_SHIPMENT_SOURCE_ID", "6")
    monkeypatch.setenv("CIP_MAILBOX_ALLOWED_SENDERS", "Jess_Mah@asus.com")

    raw = _xlsx_rfc822(
        sender="Jess_Mah@asus.com",
        filename="a.xlsx",
        body=b"PK-bytes",
        message_id="m2@asus.com",
    )
    att = attachments_from_rfc822(raw)[0]
    att = att.__class__(
        uid="99",
        message_id=att.message_id,
        from_addr=att.from_addr,
        subject=att.subject,
        received_at=att.received_at,
        filename=att.filename,
        payload=att.payload,
    )
    seen: list[str] = []

    with patch(
        "app.services.mailbox_ingest_runner.ingest_mailbox_attachment",
        return_value={"outcome": "applied", "job_id": 1},
    ) as ingest:
        with patch("app.services.mailbox_ingest_runner.SessionLocal") as sl:
            sl.return_value.__enter__.return_value = MagicMock()
            out = run_mailbox_ingest_once(fetch=lambda: [att], mark_seen=seen.append)
    assert out["ok"] is True
    assert out["count"] == 1
    assert ingest.called
    assert seen == ["99"]


def test_run_once_fetch_failure_flags_auth_and_survives(monkeypatch):
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    monkeypatch.setenv("CIP_MAILBOX_INGEST_ENABLED", "1")
    monkeypatch.setenv("CIP_MAILBOX_IMAP_USER", "warren_eliason@asus.com")
    monkeypatch.setenv("CIP_MAILBOX_IMAP_PASSWORD", "secret")
    monkeypatch.setenv("CIP_MAILBOX_SHIPMENT_SOURCE_ID", "6")
    monkeypatch.setenv("CIP_MAILBOX_ALLOWED_SENDERS", "Jess_Mah@asus.com")

    def boom():
        raise OSError("imap login failed")

    with patch("app.services.mailbox_ingest_runner.flag_mailbox_auth_failure") as flag:
        with patch("app.services.mailbox_ingest_runner.SessionLocal") as sl:
            sl.return_value.__enter__.return_value = MagicMock()
            out = run_mailbox_ingest_once(fetch=boom)
    assert out["ok"] is False
    assert out["error"] == "OSError"
    assert flag.called


def test_run_once_imap_basic_auth_disabled_is_classified(monkeypatch):
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    monkeypatch.setenv("CIP_MAILBOX_INGEST_ENABLED", "1")
    monkeypatch.setenv("CIP_MAILBOX_IMAP_USER", "warren_eliason@asus.com")
    monkeypatch.setenv("CIP_MAILBOX_IMAP_PASSWORD", "secret")
    monkeypatch.setenv("CIP_MAILBOX_SHIPMENT_SOURCE_ID", "6")
    monkeypatch.setenv("CIP_MAILBOX_ALLOWED_SENDERS", "Jess_Mah@asus.com")

    def boom():
        raise ImapBasicAuthDisabled("Basic authentication is disabled.")

    with patch("app.services.mailbox_ingest_runner.flag_mailbox_auth_failure") as flag:
        with patch("app.services.mailbox_ingest_runner.SessionLocal") as sl:
            sl.return_value.__enter__.return_value = MagicMock()
            out = run_mailbox_ingest_once(fetch=boom)
    assert out["ok"] is False
    assert out["error"] == "imap_basic_auth_disabled"
    assert flag.called


def test_spawn_is_noop_under_pytest():
    spawn_mailbox_ingest_poller()  # must not start a thread


def test_apply_unattended_provisionals_only_ready_creates():
    from app.services.mailbox_ingest.shipment_intake import apply_unattended_provisionals

    db = MagicMock()
    db.scalars.return_value.all.return_value = [11, 12, 13]
    plan = {
        "rows": [
            {"candidate_id": 11, "ready": True, "suggested_action": "map_customer"},
            {"candidate_id": 12, "ready": True, "suggested_action": "create_provisional_customer"},
            {"candidate_id": 13, "ready": False, "suggested_action": "create_provisional_customer"},
        ]
    }
    with patch(
        "app.services.mailbox_ingest.shipment_intake.build_shipment_resolution_plan_effective_sync",
        return_value=plan,
    ):
        with patch(
            "app.services.mailbox_ingest.shipment_intake.run_shipment_resolution_plan_apply_orchestrator",
            return_value={"applied": 1},
        ) as apply_plan:
            out = apply_unattended_provisionals(db, 42)
    assert apply_plan.call_args[0][2] == {"candidate_ids": [12]}
    assert out["applied"] == 1
