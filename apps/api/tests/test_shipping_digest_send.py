"""Shipping digest SMTP send (BACKLOG-132 Unit C) — mocked SMTP, no live DATA."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.models.report_delivery import ReportDelivery
from app.services.shipping_digest.config import mailer_recipients, mailer_send_enabled
from app.services.shipping_digest.recipients import DEFAULT_SHIPPING_MAILER_RECIPIENTS
from app.services.shipping_digest.smtp_check import smtp_login_check
from app.services.shipping_digest.smtp_send import (
    EmailStubRejected,
    public_smtp_error,
    send_digest_email,
    send_digest_to_recipients,
)

_MIG = (
    Path(__file__).resolve().parents[1]
    / "alembic"
    / "versions"
    / "20260818_0018_report_delivery_email_channel.py"
)


def test_migration_widens_channel_and_adds_audit_columns() -> None:
    src = _MIG.read_text(encoding="utf-8")
    assert "20260817_0017" in src
    assert "ck_report_delivery_ck_report_delivery_channel" in src
    assert "channel IN ('inbox', 'email_stub', 'email')" in src
    assert "recipient_email" in src
    assert "provider_message_id" in src
    assert "email_stub" in src


def test_model_channel_check_includes_email() -> None:
    constraint = ReportDelivery.__table_args__[0]
    sql = str(constraint.sqltext)
    assert "email" in sql
    assert "inbox" in sql
    assert "email_stub" in sql


def test_mailer_send_default_off(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("CIP_SHIPPING_MAILER_SEND", raising=False)
    monkeypatch.setenv("CIP_SHIPPING_MAILER_SEND", "0")
    from app.core.config import Settings

    assert Settings().cip_shipping_mailer_send is False
    assert mailer_send_enabled() is False


def test_default_recipients_are_the_five() -> None:
    rec = mailer_recipients()
    assert rec == DEFAULT_SHIPPING_MAILER_RECIPIENTS
    assert len(rec) == 5
    assert all(addr.endswith("@asus.com") for addr in rec)


class _FakeSMTP:
    last: "_FakeSMTP | None" = None

    def __init__(self, host: str, port: int, timeout: float | None = None) -> None:
        self.host = host
        self.port = port
        self.timeout = timeout
        self.calls: list[str] = []
        self.login_user: str | None = None
        _FakeSMTP.last = self

    def __enter__(self) -> "_FakeSMTP":
        return self

    def __exit__(self, *args: object) -> None:
        self.calls.append("quit")

    def ehlo(self) -> None:
        self.calls.append("ehlo")

    def starttls(self) -> None:
        self.calls.append("starttls")

    def login(self, user: str, password: str) -> None:
        assert password == "secret-app-password"
        self.login_user = user
        self.calls.append("login")

    def send_message(self, msg: object) -> None:
        self.calls.append("send_message")
        self.msg = msg

    def sendmail(self, *args: object, **kwargs: object) -> None:
        raise AssertionError("sendmail must not be used")

    def quit(self) -> None:
        self.calls.append("quit")


def _patch_creds_and_smtp(monkeypatch: pytest.MonkeyPatch, smtp_cls: type) -> None:
    monkeypatch.setenv("CIP_MAILBOX_IMAP_USER", "warren.eliason@gmail.com")
    monkeypatch.setenv("CIP_MAILBOX_IMAP_PASSWORD", "secret-app-password")
    monkeypatch.setenv("CIP_SHIPPING_MAILER_SMTP_HOST", "smtp.gmail.com")
    monkeypatch.setenv("CIP_SHIPPING_MAILER_SMTP_PORT", "587")
    monkeypatch.setattr("app.services.shipping_digest.smtp_send.smtplib.SMTP", smtp_cls)
    monkeypatch.setattr("app.services.shipping_digest.smtp_send.smtplib.SMTP_SSL", smtp_cls)


def test_smtp_check_ehlo_starttls_login_no_data(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_creds_and_smtp(monkeypatch, _FakeSMTP)
    result = smtp_login_check()
    assert result["ok"] is True
    calls = _FakeSMTP.last.calls if _FakeSMTP.last else []
    assert "ehlo" in calls
    assert "starttls" in calls
    assert "login" in calls
    assert "send_message" not in calls


def test_send_digest_rejects_email_stub() -> None:
    with pytest.raises(EmailStubRejected):
        send_digest_email(
            to_addr="Leigh_Sharpe@asus.com",
            subject="x",
            html_body="<p>x</p>",
            text_body="x",
            channel="email_stub",
        )


def test_send_digest_email_uses_starttls(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_creds_and_smtp(monkeypatch, _FakeSMTP)
    mid = send_digest_email(
        to_addr="Warren_Eliason@asus.com",
        subject="Shipping digest job 1159",
        html_body="<p>hello</p>",
        text_body="hello",
    )
    assert mid
    assert "send_message" in (_FakeSMTP.last.calls if _FakeSMTP.last else [])
    assert "starttls" in (_FakeSMTP.last.calls if _FakeSMTP.last else [])


def test_send_to_recipients_records_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CIP_MAILBOX_IMAP_USER", "warren.eliason@gmail.com")
    monkeypatch.setenv("CIP_MAILBOX_IMAP_PASSWORD", "secret-app-password")

    def _boom(**kwargs: object) -> str:
        raise RuntimeError("simulated smtp down")

    monkeypatch.setattr(
        "app.services.shipping_digest.smtp_send.send_digest_email",
        _boom,
    )
    results = send_digest_to_recipients(
        recipients=("Leigh_Sharpe@asus.com", "Wayne_Holt@asus.com"),
        subject="Shipping digest",
        html_body="<p>x</p>",
        text_body="x",
    )
    assert len(results) == 2
    assert all(r["status"] == "failed" for r in results)
    assert all(r["error_message"] for r in results)
    assert all(r["recipient_email"].endswith("@asus.com") for r in results)


def test_public_smtp_error_strips_secret() -> None:
    err = public_smtp_error(RuntimeError("auth failed secret-app-password"), secret="secret-app-password")
    assert "secret-app-password" not in err
    assert "***" in err


def test_dsi_apply_still_does_not_import_digest() -> None:
    src = (
        Path(__file__).resolve().parents[1]
        / "app"
        / "services"
        / "imports"
        / "dsi_apply_completion.py"
    ).read_text(encoding="utf-8")
    assert "shipping_digest" not in src
    assert "dispatch_shipping_digest" not in src
