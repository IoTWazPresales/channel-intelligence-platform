"""API-lifespan mailbox poller — same shape as report_schedule_runner (Windows, no Celery beat)."""

from __future__ import annotations

import logging
import threading
import time
from typing import Any, Callable

from app.db.session_sync import SessionLocal
from app.services.mailbox_ingest.config import (
    mailbox_allowed_senders,
    mailbox_env_disabled_reason,
    mailbox_folder,
    mailbox_graph_folder,
    mailbox_imap_host,
    mailbox_imap_password,
    mailbox_imap_port,
    mailbox_imap_user,
    mailbox_ingest_enabled,
    mailbox_ingest_poll_interval_seconds,
    mailbox_shipment_source_id,
    mailbox_transport,
)
from app.services.mailbox_ingest.graph_auth import GraphAuthNeeded
from app.services.mailbox_ingest.graph_fetch import (
    fetch_unseen_shipment_attachments_graph,
    mark_graph_message_read,
)
from app.services.mailbox_ingest.imap_fetch import (
    ImapBasicAuthDisabled,
    MailboxAttachment,
    fetch_unseen_shipment_attachments,
    mark_uid_seen,
)
from app.services.mailbox_ingest.shipment_intake import (
    flag_mailbox_auth_failure,
    flag_mailbox_message_failure,
    ingest_mailbox_attachment,
)

logger = logging.getLogger(__name__)

_poller_lock = threading.Lock()
_poller_started = False

FetchFn = Callable[[], list[MailboxAttachment]]
MarkSeenFn = Callable[[str], None]


def _default_fetch() -> list[MailboxAttachment]:
    if mailbox_transport() == "graph":
        return fetch_unseen_shipment_attachments_graph(
            user=mailbox_imap_user(),
            folder=mailbox_graph_folder(),
            allowed_senders=mailbox_allowed_senders(),
        )
    return fetch_unseen_shipment_attachments(
        host=mailbox_imap_host(),
        port=mailbox_imap_port(),
        user=mailbox_imap_user(),
        password=mailbox_imap_password(),
        folder=mailbox_folder(),
        allowed_senders=mailbox_allowed_senders(),
    )


def _default_mark_seen(uid: str) -> None:
    if mailbox_transport() == "graph":
        mark_graph_message_read(user=mailbox_imap_user(), message_id=uid)
        return
    mark_uid_seen(
        host=mailbox_imap_host(),
        port=mailbox_imap_port(),
        user=mailbox_imap_user(),
        password=mailbox_imap_password(),
        folder=mailbox_folder(),
        uid=uid,
    )


def run_mailbox_ingest_once(
    *,
    fetch: FetchFn | None = None,
    mark_seen: MarkSeenFn | None = None,
) -> dict[str, Any]:
    """One poll pass. Never raises to the lifespan loop (mirror run_due_schedules_safe)."""
    reason = mailbox_env_disabled_reason()
    if reason:
        return {"ok": True, "skipped": True, "reason": reason}

    source_id = mailbox_shipment_source_id()
    if source_id is None:
        return {"ok": True, "skipped": True, "reason": "no_source_id"}

    fetch_fn = fetch or _default_fetch
    seen_fn = mark_seen or _default_mark_seen
    results: list[dict[str, Any]] = []
    try:
        attachments = fetch_fn()
    except GraphAuthNeeded as exc:
        logger.warning("FLAG mailbox Graph token missing: %s", exc)
        with SessionLocal() as db:
            flag_mailbox_auth_failure(db, source_id=source_id, error=str(exc))
        return {"ok": False, "error": "graph_auth_needed", "results": []}
    except ImapBasicAuthDisabled as exc:
        logger.warning(
            "FLAG mailbox IMAP basic auth is disabled on this Microsoft 365 tenant (%s). "
            "Set CIP_MAILBOX_GRAPH_CLIENT_ID (Entra app, Mail.ReadWrite) and CIP_MAILBOX_TRANSPORT=graph, "
            "then from apps/api run: .venv\\Scripts\\python.exe -m app.services.mailbox_ingest.graph_login",
            exc,
        )
        with SessionLocal() as db:
            flag_mailbox_auth_failure(db, source_id=source_id, error=str(exc))
        return {"ok": False, "error": "imap_basic_auth_disabled", "results": []}
    except Exception as exc:
        logger.exception("FLAG mailbox fetch failed")
        with SessionLocal() as db:
            flag_mailbox_auth_failure(db, source_id=source_id, error=str(exc))
        return {"ok": False, "error": type(exc).__name__, "results": []}

    seen_uids: set[str] = set()
    for att in attachments:
        try:
            with SessionLocal() as db:
                out = ingest_mailbox_attachment(db, source_id=source_id, attachment=att)
            results.append({"file": att.filename, **out})
            if att.uid and att.uid not in seen_uids:
                try:
                    seen_fn(att.uid)
                    seen_uids.add(att.uid)
                except Exception:
                    logger.exception("FLAG mailbox mark-seen failed uid=%s job still committed", att.uid)
        except Exception as exc:
            logger.exception("FLAG mailbox attachment ingest failed file=%s", att.filename)
            with SessionLocal() as db:
                flag_mailbox_message_failure(db, source_id=source_id, attachment=att, error=str(exc))
            results.append({"file": att.filename, "outcome": "failed", "error": type(exc).__name__})

    return {"ok": True, "count": len(attachments), "results": results}


def run_mailbox_ingest_safe(*, reason: str) -> dict[str, Any]:
    try:
        out = run_mailbox_ingest_once()
        logger.warning(
            "mailbox ingest poll reason=%s %s",
            reason,
            {k: out.get(k) for k in ("ok", "skipped", "count", "error")},
        )
        return out
    except Exception:
        logger.exception("mailbox ingest poll failed reason=%s", reason)
        return {"ok": False, "reason": reason}


def spawn_mailbox_ingest_poller() -> None:
    """Catch up immediately, then poll while this API process stays up. No Celery beat."""
    global _poller_started
    if not mailbox_ingest_enabled():
        why = mailbox_env_disabled_reason()
        logger.warning("mailbox ingest poller skipped (%s)", why or "disabled")
        return
    with _poller_lock:
        if _poller_started:
            return
        _poller_started = True
    interval = mailbox_ingest_poll_interval_seconds()
    transport = mailbox_transport()

    def _loop() -> None:
        run_mailbox_ingest_safe(reason="startup")
        while True:
            time.sleep(interval)
            run_mailbox_ingest_safe(reason="interval")

    threading.Thread(target=_loop, name="cip-mailbox-ingest-poll", daemon=True).start()
    logger.warning(
        "mailbox ingest poller started interval=%ss transport=%s folder=%s",
        interval,
        transport,
        mailbox_graph_folder() if transport == "graph" else mailbox_folder(),
    )
