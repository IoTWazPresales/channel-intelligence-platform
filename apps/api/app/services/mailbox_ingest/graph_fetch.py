"""Microsoft Graph fetch of spreadsheet attachments. Same MailboxAttachment as IMAP."""

from __future__ import annotations

import base64
import logging
from typing import Any
from urllib.parse import quote

import httpx

from app.services.mailbox_ingest.graph_auth import acquire_graph_access_token
from app.services.mailbox_ingest.imap_fetch import (
    MailboxAttachment,
    filename_is_shipment_workbook,
    normalize_email_addr,
    normalize_message_id,
    sender_is_allowlisted,
)

logger = logging.getLogger(__name__)

GRAPH_ROOT = "https://graph.microsoft.com/v1.0"
_HTTP_TIMEOUT_S = 30.0
_PAGE_SIZE = 25


def attachments_from_graph_message(
    message: dict[str, Any],
    file_attachments: list[dict[str, Any]],
    *,
    allowed_senders: frozenset[str],
) -> list[MailboxAttachment]:
    """Pure parse of one Graph message + its file attachments (no HTTP)."""
    from_hdr = (
        ((message.get("from") or {}).get("emailAddress") or {}).get("address")
        or ((message.get("sender") or {}).get("emailAddress") or {}).get("address")
        or ""
    )
    if not sender_is_allowlisted(from_hdr, allowed_senders):
        logger.info(
            "mailbox ingest skipped non-allowlisted sender graph_id=%s from=%s",
            message.get("id"),
            normalize_email_addr(from_hdr),
        )
        return []
    uid = str(message.get("id") or "")
    message_id = normalize_message_id(message.get("internetMessageId")) or uid
    subject = str(message.get("subject") or "(no subject)")
    received_at = str(message.get("receivedDateTime") or "") or None
    from_addr = normalize_email_addr(from_hdr)
    out: list[MailboxAttachment] = []
    for att in file_attachments:
        filename = str(att.get("name") or "").strip()
        if not filename_is_shipment_workbook(filename):
            continue
        raw_b64 = att.get("contentBytes")
        if not isinstance(raw_b64, str) or not raw_b64:
            continue
        try:
            payload = base64.b64decode(raw_b64)
        except Exception:
            logger.warning("FLAG mailbox Graph attachment not base64 file=%s", filename)
            continue
        if not payload:
            continue
        out.append(
            MailboxAttachment(
                uid=uid,
                message_id=message_id,
                from_addr=from_addr,
                subject=subject,
                received_at=received_at,
                filename=filename,
                payload=payload,
            )
        )
    return out


def fetch_unseen_shipment_attachments_graph(
    *,
    user: str,
    folder: str,
    allowed_senders: frozenset[str],
    token: str | None = None,
    delegated: bool | None = None,
    client: httpx.Client | None = None,
) -> list[MailboxAttachment]:
    """Unread inbox messages with spreadsheet attachments from allowlisted senders.

    Non-allowlisted unread mail is left unread.
    """
    if token is None or delegated is None:
        token, delegated_flag = acquire_graph_access_token()
        delegated = delegated_flag
    headers = {"Authorization": f"Bearer {token}"}
    base = _graph_mailbox_base(user, delegated=bool(delegated))
    folder_id = folder.strip() or "inbox"
    own_client = client is None
    http = client or httpx.Client(timeout=_HTTP_TIMEOUT_S)
    try:
        url = f"{base}/mailFolders/{quote(folder_id, safe='')}/messages"
        resp = http.get(
            url,
            headers=headers,
            params={
                "$filter": "isRead eq false and hasAttachments eq true",
                "$select": "id,internetMessageId,from,sender,subject,receivedDateTime,hasAttachments",
                "$top": str(_PAGE_SIZE),
            },
        )
        _raise_graph(resp, "list unread messages")
        messages = list((resp.json() or {}).get("value") or [])
        found: list[MailboxAttachment] = []
        for message in messages:
            mid = str(message.get("id") or "")
            if not mid:
                continue
            att_url = f"{base}/messages/{quote(mid, safe='')}/attachments"
            att_resp = http.get(att_url, headers=headers)
            _raise_graph(att_resp, "list attachments")
            file_atts = [
                a
                for a in list((att_resp.json() or {}).get("value") or [])
                if _is_file_attachment(a)
            ]
            parts = attachments_from_graph_message(
                message, file_atts, allowed_senders=allowed_senders
            )
            if not parts:
                if sender_is_allowlisted(
                    ((message.get("from") or {}).get("emailAddress") or {}).get("address") or "",
                    allowed_senders,
                ):
                    logger.warning(
                        "FLAG mailbox Graph message id=%s from=%s has no xlsx/xlsm/csv attachment",
                        mid,
                        normalize_email_addr(
                            ((message.get("from") or {}).get("emailAddress") or {}).get("address")
                        ),
                    )
                continue
            found.extend(parts)
        return found
    finally:
        if own_client:
            http.close()


def mark_graph_message_read(
    *,
    user: str,
    message_id: str,
    token: str | None = None,
    delegated: bool | None = None,
    client: httpx.Client | None = None,
) -> None:
    if not message_id:
        return
    if token is None or delegated is None:
        token, delegated_flag = acquire_graph_access_token()
        delegated = delegated_flag
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    base = _graph_mailbox_base(user, delegated=bool(delegated))
    own_client = client is None
    http = client or httpx.Client(timeout=_HTTP_TIMEOUT_S)
    try:
        url = f"{base}/messages/{quote(message_id, safe='')}"
        resp = http.patch(url, headers=headers, json={"isRead": True})
        _raise_graph(resp, "mark message read")
    finally:
        if own_client:
            http.close()


def _graph_mailbox_base(user: str, *, delegated: bool) -> str:
    if delegated:
        return f"{GRAPH_ROOT}/me"
    return f"{GRAPH_ROOT}/users/{quote(user, safe='')}"


def _is_file_attachment(att: dict[str, Any]) -> bool:
    odata = str(att.get("@odata.type") or "")
    if "fileAttachment" in odata:
        return True
    return bool(att.get("contentBytes") and att.get("name"))


def _raise_graph(resp: httpx.Response, action: str) -> None:
    if resp.status_code < 400:
        return
    snippet = (resp.text or "")[:400]
    raise RuntimeError(f"Graph {action} failed HTTP {resp.status_code}: {snippet}")
