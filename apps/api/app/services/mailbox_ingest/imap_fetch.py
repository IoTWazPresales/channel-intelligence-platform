"""IMAP fetch of spreadsheet attachments. M365 tenants with basic auth off must use Graph."""

from __future__ import annotations

import email
import hashlib
import imaplib
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from email.header import decode_header, make_header
from email.message import Message
from email.utils import parseaddr, parsedate_to_datetime
from typing import Any

logger = logging.getLogger(__name__)

SHIPMENT_SUFFIXES = (".xlsx", ".xlsm", ".csv")
_IMAP_TIMEOUT_S = 30
_MAX_FETCH_PER_POLL = 25
_LOOKBACK_DAYS = 3
_IMAP_MONTHS = (
    "Jan",
    "Feb",
    "Mar",
    "Apr",
    "May",
    "Jun",
    "Jul",
    "Aug",
    "Sep",
    "Oct",
    "Nov",
    "Dec",
)
_JESS_SENDER = "jess_mah@asus.com"


class ImapBasicAuthDisabled(RuntimeError):
    """Microsoft 365 rejected username/password IMAP. Use Graph on the same intake path."""


@dataclass(frozen=True)
class MailboxAttachment:
    uid: str
    message_id: str
    from_addr: str
    subject: str
    received_at: str | None
    filename: str
    payload: bytes

    @property
    def checksum_sha256(self) -> str:
        return hashlib.sha256(self.payload).hexdigest()


def normalize_email_addr(value: str | None) -> str:
    _, addr = parseaddr(value or "")
    return (addr or "").strip().lower()


def normalize_message_id(value: str | None) -> str:
    raw = (value or "").strip()
    if raw.startswith("<") and raw.endswith(">") and len(raw) > 2:
        raw = raw[1:-1]
    return raw.strip()


def sender_is_allowlisted(from_header: str, allowed: frozenset[str]) -> bool:
    if not allowed:
        return False
    addr = normalize_email_addr(from_header)
    return bool(addr) and addr in allowed


def filename_is_shipment_workbook(filename: str) -> bool:
    lower = (filename or "").strip().lower()
    return any(lower.endswith(suf) for suf in SHIPMENT_SUFFIXES)


def _decode_filename(raw: str | None) -> str:
    if not raw:
        return ""
    try:
        return str(make_header(decode_header(raw))).strip()
    except Exception:
        return str(raw).strip()


def attachments_from_rfc822(raw_rfc822: bytes) -> list[MailboxAttachment]:
    """Parse one RFC822 message into shipment-shaped attachments (uid left empty)."""
    msg = email.message_from_bytes(raw_rfc822)
    from_addr = normalize_email_addr(msg.get("From"))
    message_id = normalize_message_id(msg.get("Message-ID") or msg.get("Message-Id"))
    subject = _decode_filename(msg.get("Subject")) or "(no subject)"
    received_at: str | None = None
    date_hdr = msg.get("Date")
    if date_hdr:
        try:
            received_at = parsedate_to_datetime(date_hdr).isoformat()
        except Exception:
            received_at = str(date_hdr)[:64]
    out: list[MailboxAttachment] = []
    for part in _iter_parts(msg):
        filename = _part_filename(part)
        if not filename_is_shipment_workbook(filename):
            continue
        payload = part.get_payload(decode=True)
        if not isinstance(payload, (bytes, bytearray)) or not payload:
            continue
        out.append(
            MailboxAttachment(
                uid="",
                message_id=message_id or hashlib.sha256(payload).hexdigest(),
                from_addr=from_addr,
                subject=subject,
                received_at=received_at,
                filename=filename,
                payload=bytes(payload),
            )
        )
    return out


def _part_filename(part: Message) -> str:
    name = _decode_filename(part.get_filename())
    if name:
        return name
    return _decode_filename(part.get_param("name", header="content-type") or "")


def _as_message(payload: Any) -> Message | None:
    if isinstance(payload, Message):
        return payload
    if isinstance(payload, (bytes, bytearray)):
        return email.message_from_bytes(bytes(payload))
    if isinstance(payload, str):
        return email.message_from_string(payload)
    return None


def _iter_parts(msg: Message) -> list[Message]:
    """Leaf parts, including attachments nested in forwarded message/rfc822 wrappers."""
    if msg.get_content_type() == "message/rfc822":
        payload = msg.get_payload()
        inner_raw = payload[0] if isinstance(payload, list) and payload else payload
        inner = _as_message(inner_raw)
        if inner is not None:
            return _iter_parts(inner)
        return []
    if msg.is_multipart():
        out: list[Message] = []
        for part in msg.get_payload() or []:
            if isinstance(part, Message):
                out.extend(_iter_parts(part))
        return out
    return [msg]


def imap_since_date(*, days: int = _LOOKBACK_DAYS, now: datetime | None = None) -> str:
    """IMAP date atom (English month). Do not use locale strftime."""
    dt = (now or datetime.now(timezone.utc)) - timedelta(days=days)
    return f"{dt.day}-{_IMAP_MONTHS[dt.month - 1]}-{dt.year}"


def imap_allowlist_since_criteria(allowed: frozenset[str], *, since: str) -> tuple[str, ...]:
    """IMAP SEARCH: SINCE <date> AND nested OR FROM allowlisted addresses.

    Intentionally not UNSEEN: opening a forward in Gmail marks it read; checksum
    dedupe skips already-ingested files.
    """
    addrs = tuple(sorted(a.strip() for a in allowed if a.strip()))
    parts: list[str] = ["SINCE", since]
    if not addrs:
        return tuple(parts)
    for i, addr in enumerate(addrs):
        if i < len(addrs) - 1:
            parts.append("OR")
        parts.extend(["FROM", addr])
    return tuple(parts)


def imap_unseen_allowlist_criteria(allowed: frozenset[str]) -> tuple[str, ...]:
    """Kept for tests / callers; live fetch uses SINCE, not UNSEEN."""
    addrs = tuple(sorted(a.strip() for a in allowed if a.strip()))
    if not addrs:
        return ("UNSEEN",)
    parts: list[str] = ["UNSEEN"]
    for i, addr in enumerate(addrs):
        if i < len(addrs) - 1:
            parts.append("OR")
        parts.extend(["FROM", addr])
    return tuple(parts)


def _uids_from_search(data: Any) -> list[str]:
    if not data or data[0] is None:
        return []
    return [u.decode("ascii") if isinstance(u, bytes) else str(u) for u in data[0].split() if u]


def _search_candidate_uids(
    client: imaplib.IMAP4,
    *,
    allowed_senders: frozenset[str],
) -> list[str]:
    since = imap_since_date()
    typ, data = client.uid("SEARCH", None, *imap_allowlist_since_criteria(allowed_senders, since=since))
    if typ != "OK":
        raise RuntimeError(f"IMAP SEARCH failed: {typ}")
    return _uids_from_search(data)


def fetch_unseen_shipment_attachments(
    *,
    host: str,
    port: int,
    user: str,
    password: str,
    folder: str,
    allowed_senders: frozenset[str],
) -> list[MailboxAttachment]:
    """Fetch recent allowlisted messages; return spreadsheet attachments.

    Uses SINCE (not UNSEEN) so a forward opened in Gmail is still eligible.
    BODY.PEEK so fetch does not mark mail read. Already-ingested files skip via checksum.
    """
    client = imaplib.IMAP4_SSL(host, port, timeout=_IMAP_TIMEOUT_S)
    try:
        _imap_login(client, user, password)
        typ, _ = client.select(folder, readonly=False)
        if typ != "OK":
            raise RuntimeError(f"IMAP select {folder!r} failed: {typ}")
        uids = _search_candidate_uids(client, allowed_senders=allowed_senders)
        if len(uids) > _MAX_FETCH_PER_POLL:
            logger.warning(
                "mailbox IMAP truncating allowlisted %s -> last %s",
                len(uids),
                _MAX_FETCH_PER_POLL,
            )
            uids = uids[-_MAX_FETCH_PER_POLL:]
        found: list[MailboxAttachment] = []
        for uid in uids:
            typ, fetched = client.uid("FETCH", uid, "(BODY.PEEK[])")
            if typ != "OK" or not fetched:
                logger.warning("FLAG mailbox IMAP FETCH failed uid=%s typ=%s", uid, typ)
                continue
            raw = _rfc822_from_fetch(fetched)
            if not raw:
                continue
            msg = email.message_from_bytes(raw)
            from_hdr = msg.get("From") or ""
            if not sender_is_allowlisted(from_hdr, allowed_senders):
                logger.info(
                    "mailbox ingest skipped non-allowlisted sender uid=%s from=%s",
                    uid,
                    normalize_email_addr(from_hdr),
                )
                continue
            parts = attachments_from_rfc822(raw)
            if not parts:
                from_addr = normalize_email_addr(from_hdr)
                if from_addr == _JESS_SENDER:
                    logger.warning(
                        "FLAG mailbox message uid=%s from=%s has no xlsx/xlsm/csv attachment",
                        uid,
                        from_addr,
                    )
                else:
                    logger.info(
                        "mailbox ingest skipped no spreadsheet uid=%s from=%s",
                        uid,
                        from_addr,
                    )
                continue
            for part in parts:
                found.append(
                    MailboxAttachment(
                        uid=uid,
                        message_id=part.message_id,
                        from_addr=part.from_addr,
                        subject=part.subject,
                        received_at=part.received_at,
                        filename=part.filename,
                        payload=part.payload,
                    )
                )
        return found
    finally:
        try:
            client.logout()
        except Exception:
            pass


def mark_uid_seen(
    *,
    host: str,
    port: int,
    user: str,
    password: str,
    folder: str,
    uid: str,
) -> None:
    if not uid:
        return
    client = imaplib.IMAP4_SSL(host, port, timeout=_IMAP_TIMEOUT_S)
    try:
        _imap_login(client, user, password)
        typ, _ = client.select(folder, readonly=False)
        if typ != "OK":
            raise RuntimeError(f"IMAP select {folder!r} failed: {typ}")
        client.uid("STORE", uid, "+FLAGS", r"(\Seen)")
    finally:
        try:
            client.logout()
        except Exception:
            pass


def _imap_error_text(exc: BaseException) -> str:
    parts: list[str] = []
    for arg in getattr(exc, "args", ()) or ():
        if isinstance(arg, bytes):
            parts.append(arg.decode("utf-8", "replace"))
        else:
            parts.append(str(arg))
    return " ".join(parts) or str(exc)


def _imap_login(client: imaplib.IMAP4, user: str, password: str) -> None:
    try:
        client.login(user, password)
    except imaplib.IMAP4.error as exc:
        text = _imap_error_text(exc)
        if "basic authentication is disabled" in text.lower():
            raise ImapBasicAuthDisabled(text) from exc
        raise


def _rfc822_from_fetch(fetched: Any) -> bytes | None:
    for item in fetched:
        if not isinstance(item, tuple) or len(item) < 2:
            continue
        blob = item[1]
        if isinstance(blob, bytes) and blob:
            return blob
    return None
