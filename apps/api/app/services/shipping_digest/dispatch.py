"""Shipping digest dispatch after shipment apply. Inbox always; SMTP behind CIP_SHIPPING_MAILER_SEND."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import AsyncSessionLocal
from app.models.report_delivery import ReportDelivery
from app.services.shipping_digest.build import build_shipping_digest
from app.services.shipping_digest.config import mailer_recipients, mailer_send_enabled
from app.services.shipping_digest.render import render_html, render_text
from app.services.shipping_digest.smtp_send import send_digest_to_recipients

logger = logging.getLogger(__name__)

_PLACEHOLDER_TOKENS = ("lorem", "TODO", "pending owner", "placeholder")


def _digest_subject(*, import_job_id: Any, preview: bool) -> str:
    job_bit = f" job {import_job_id}" if import_job_id is not None else ""
    prefix = "[PREVIEW] " if preview else ""
    return f"{prefix}Shipping digest{job_bit}"


async def _write_preview_row(
    db: AsyncSession,
    *,
    tenant_id: str,
    digest: dict[str, Any],
    html_body: str,
    text_body: str,
    preview: bool,
) -> ReportDelivery:
    recipients = digest.get("intended_recipients") or list(mailer_recipients())
    vintage = dict(digest.get("data_vintage") or {})
    job = vintage.get("source_job_id")
    subject = _digest_subject(import_job_id=job, preview=preview)
    header = (
        "Would send To: " if preview else "Sent / attempted To: "
    ) + ", ".join(str(x) for x in recipients) + "\n"
    summary = (header + text_body)[:2000]
    row = ReportDelivery(
        tenant_id=tenant_id,
        recipient_user_id=None,
        saved_report_id=None,
        channel="inbox",
        trigger="import_event",
        format="xlsx",
        status="delivered",
        subject=subject,
        body_summary=summary,
        data_vintage=vintage,
        missing_data_alert=False,
        metric_key="shipping_digest",
        value_preview=str(sum(len(s.get("rows") or []) for s in digest.get("sections") or [])),
        storage_key=html_body,
        error_message=None,
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return row


async def _write_email_audit_rows(
    db: AsyncSession,
    *,
    tenant_id: str,
    digest: dict[str, Any],
    results: list[dict[str, Any]],
    subject: str,
    text_body: str,
) -> list[ReportDelivery]:
    vintage = dict(digest.get("data_vintage") or {})
    vintage["html_preview"] = False
    rows: list[ReportDelivery] = []
    for item in results:
        status = str(item.get("status") or "failed")
        addr = str(item.get("recipient_email") or "")
        err = item.get("error_message")
        row = ReportDelivery(
            tenant_id=tenant_id,
            recipient_user_id=None,
            saved_report_id=None,
            channel="email",
            trigger="import_event",
            format="xlsx",
            status=status if status in ("delivered", "failed") else "failed",
            subject=subject,
            body_summary=(f"To: {addr}\n" + text_body)[:2000],
            data_vintage=vintage,
            missing_data_alert=False,
            metric_key="shipping_digest",
            value_preview=addr,
            storage_key=None,
            error_message=err,
            recipient_email=addr or None,
            provider_message_id=item.get("provider_message_id"),
        )
        db.add(row)
        rows.append(row)
    if rows:
        await db.commit()
        for row in rows:
            await db.refresh(row)
    return rows


async def dispatch_shipping_digest_async(
    *,
    tenant_id: str = "default",
    import_job_id: int | None = None,
) -> dict[str, Any]:
    sending = mailer_send_enabled()
    async with AsyncSessionLocal() as db:
        digest = await build_shipping_digest(
            db, tenant_id=tenant_id, import_job_id=import_job_id
        )
        html_body = render_html(digest)
        text_body = render_text(digest)
        lowered = (html_body + text_body).lower()
        for tok in _PLACEHOLDER_TOKENS:
            if tok in lowered:
                raise ValueError(f"digest renderer emitted placeholder token {tok!r}")
        inbox = await _write_preview_row(
            db,
            tenant_id=tenant_id,
            digest=digest,
            html_body=html_body,
            text_body=text_body,
            preview=not sending,
        )
        email_ids: list[int] = []
        email_statuses: list[str] = []
        if sending:
            job = (digest.get("data_vintage") or {}).get("source_job_id")
            subject = _digest_subject(import_job_id=job, preview=False)
            results = send_digest_to_recipients(
                recipients=list(digest.get("intended_recipients") or mailer_recipients()),
                subject=subject,
                html_body=html_body,
                text_body=text_body,
            )
            email_rows = await _write_email_audit_rows(
                db,
                tenant_id=tenant_id,
                digest=digest,
                results=results,
                subject=subject,
                text_body=text_body,
            )
            email_ids = [int(r.id) for r in email_rows]
            email_statuses = [str(r.status) for r in email_rows]
        return {
            "ok": True,
            "delivery_id": int(inbox.id),
            "preview": not sending,
            "sent": sending,
            "email_delivery_ids": email_ids,
            "email_statuses": email_statuses,
        }


def dispatch_shipping_digest(*, tenant_id: str = "default", import_job_id: int | None = None) -> None:
    """Best-effort; never raises to the apply caller."""
    try:
        asyncio.run(
            dispatch_shipping_digest_async(tenant_id=tenant_id, import_job_id=import_job_id)
        )
    except RuntimeError:
        logger.exception("shipping digest dispatch skipped; running loop tenant_id=%s", tenant_id)
    except Exception:
        logger.exception(
            "shipping digest dispatch failed tenant_id=%s job_id=%s; apply remains complete",
            tenant_id,
            import_job_id,
        )
