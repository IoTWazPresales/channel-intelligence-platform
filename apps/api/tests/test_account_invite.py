"""Invite mail carries a link, never a password, and logs never carry the token."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from app.core.password import hash_session_token
from app.services.account_invite import compose_invite, new_invite_row


def test_invite_message_is_a_link_with_no_password_value():
    link = "http://127.0.0.1:3000/set-password?token=example-link-token"
    subject, text, html = compose_invite(link)
    assert "Set your Channel Intelligence password" == subject
    assert link in text
    assert "72 hours" in text
    assert "example-link-token" in html
    assert "password is" not in text.lower()
    assert "temporary password" not in text.lower()


def test_invite_row_stores_the_hash_only():
    raw, row = new_invite_row(7, datetime.now(timezone.utc))
    assert row.user_id == 7
    assert row.token_hash == hash_session_token(raw)
    assert raw not in row.token_hash
    assert row.used_at is None


def test_send_failure_log_omits_the_token(caplog, monkeypatch):
    from app.services import account_invite

    captured: dict[str, str] = {}

    def boom(**kwargs):
        captured["text"] = kwargs["text_body"]
        raise RuntimeError("smtp rejected " + kwargs["text_body"])

    monkeypatch.setattr(account_invite, "send_digest_email", boom)

    class User:
        id = 4
        email = "person@example.com"

    class Result:
        def scalars(self):
            return self

        def all(self):
            return []

    class Db:
        def __init__(self):
            self.added = []

        async def execute(self, _stmt):
            return Result()

        def add(self, row):
            self.added.append(row)

        async def flush(self):
            return None

    db = Db()
    with caplog.at_level(logging.WARNING):
        sent = asyncio.run(account_invite.issue_invite(db, User()))
    assert sent is False
    assert db.added[0].used_at is not None
    assert "example" not in caplog.text
    assert "token=" not in caplog.text
    assert "smtp rejected" not in caplog.text
    assert "send_failed user_id=4 error_type=RuntimeError" in caplog.text
    assert "token=" in captured["text"]
