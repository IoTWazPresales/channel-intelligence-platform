"""Customer settlement sign-off for one case.

The raw token is only in the outbound mail. The database stores its hash.
A link opens that case's settlement summary and nothing else. It expires,
and a planner can revoke it before the customer decides.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from html import escape
from typing import Any
from urllib.parse import quote

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.password import hash_session_token, new_session_token
from app.models.cpor import CporCase, CporCaseEvent
from app.models.cpor_approval import CporCaseApprovalLink
from app.models.dimensions import DimCustomer
from app.services.cpor.settlement import build_settlement_consolidation
from app.services.shipping_digest.smtp_send import send_digest_email

logger = logging.getLogger(__name__)

LINK_TTL = timedelta(days=7)
PUBLIC_MISS = "This link is not valid. Ask the planner to send a new one."
PUBLIC_KEYS = (
    "case_code",
    "case_name",
    "customer_name",
    "window_start",
    "window_end",
    "currency",
    "export_version",
    "lines",
    "support_total",
)


def approval_link(raw_token: str) -> str:
    origin = get_settings().cip_public_web_origin.strip().rstrip("/")
    return f"{origin}/case-approval?token={quote(raw_token, safe='')}"


def compose_approval_mail(link: str, case_code: str) -> tuple[str, str, str]:
    subject = f"Settlement sign-off for {case_code}"
    text = (
        f"Please review settlement for case {case_code}.\n\n"
        "This link opens that case only. It expires in 7 days and can be withdrawn.\n"
        f"{link}\n\n"
        "If you were not expecting this, you can ignore it.\n"
    )
    safe = escape(link, quote=True)
    html = (
        f"<p>Please review settlement for case {escape(case_code)}.</p>"
        "<p>This link opens that case only. It expires in 7 days and can be withdrawn.</p>"
        f'<p><a href="{safe}">Review this case</a></p>'
        "<p>If you were not expecting this, you can ignore it.</p>"
    )
    return subject, text, html


def link_block(link: Any, *, now: datetime, current_version: int) -> str | None:
    """Why a link cannot be used. None means the customer may read and decide."""
    if link is None:
        return "missing"
    if link.revoked_at is not None:
        return "revoked"
    if link.decided_at is not None:
        return "decided"
    expires = link.expires_at
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=timezone.utc)
    if expires <= now:
        return "expired"
    if int(link.export_version) != int(current_version):
        return "stale"
    return None


def public_summary(
    consolidation: dict[str, Any],
    *,
    case_code: str,
    case_name: str | None,
    customer_name: str,
    currency: str,
    export_version: int,
) -> dict[str, Any]:
    """The only payload a customer link may return."""
    lines = []
    for row in consolidation.get("lines") or []:
        product = (
            row.get("product_name")
            or row.get("product_sales_model_name")
            or row.get("product_sku")
            or "Product"
        )
        lines.append(
            {
                "product": product,
                "estimate_qty": row.get("estimate_qty"),
                "result_qty": row.get("result_qty"),
                "support_per_unit": row.get("support_unit"),
                "support_total": row.get("ttl_result"),
            }
        )
    desk = consolidation.get("desk") or {}
    summary = {
        "case_code": case_code,
        "case_name": case_name,
        "customer_name": customer_name,
        "window_start": consolidation.get("window_start"),
        "window_end": consolidation.get("window_end"),
        "currency": currency,
        "export_version": int(export_version),
        "lines": lines,
        "support_total": desk.get("customer_amount"),
    }
    return {key: summary[key] for key in PUBLIC_KEYS}


def signoff_event(
    *,
    decision: str,
    signer_name: str,
    comment: str,
    export_version: int,
    recipient_email: str,
    decided_at: datetime,
) -> dict[str, Any]:
    return {
        "event_type": "customer_settlement_signoff",
        "actor": signer_name,
        "payload": {
            "decision": decision,
            "signer_name": signer_name,
            "comment": comment,
            "export_version": int(export_version),
            "recipient_email": recipient_email,
            "decided_at": decided_at.isoformat(),
        },
    }


def planner_view(link: Any, *, now: datetime, current_version: int) -> dict[str, Any]:
    if link is None:
        return {"state": "none"}
    block = link_block(link, now=now, current_version=current_version)
    return {
        "state": "open" if block is None else block,
        "recipient_email": link.recipient_email,
        "export_version": int(link.export_version),
        "expires_at": link.expires_at.isoformat(),
        "decided_at": link.decided_at.isoformat() if link.decided_at else None,
        "decision": link.decision,
        "signer_name": link.signer_name,
    }


def _latest(session: Session, case_id: int) -> CporCaseApprovalLink | None:
    return session.scalars(
        select(CporCaseApprovalLink)
        .where(CporCaseApprovalLink.case_id == case_id)
        .order_by(CporCaseApprovalLink.id.desc())
    ).first()


def _revoke_open(session: Session, case_id: int, now: datetime) -> int:
    rows = session.scalars(
        select(CporCaseApprovalLink).where(
            CporCaseApprovalLink.case_id == case_id,
            CporCaseApprovalLink.revoked_at.is_(None),
            CporCaseApprovalLink.decided_at.is_(None),
        )
    ).all()
    for row in rows:
        row.revoked_at = now
    return len(rows)


def load_case_customer(session: Session, case_id: int) -> tuple[CporCase, str]:
    case = session.get(CporCase, case_id)
    if case is None:
        raise LookupError("case")
    customer = session.get(DimCustomer, case.customer_id)
    name = customer.name if customer is not None else "Customer"
    return case, name


def read_public(session: Session, raw_token: str, now: datetime | None = None) -> dict[str, Any]:
    now = now or datetime.now(timezone.utc)
    link = _link_by_token(session, raw_token)
    if link is None:
        raise PermissionError(PUBLIC_MISS)
    case, customer_name = load_case_customer(session, link.case_id)
    if link_block(link, now=now, current_version=int(case.export_version)) is not None:
        raise PermissionError(PUBLIC_MISS)
    summary = public_summary(
        build_settlement_consolidation(session, case.id),
        case_code=case.case_code,
        case_name=case.case_name,
        customer_name=customer_name,
        currency=case.currency_code,
        export_version=int(link.export_version),
    )
    return summary


def decide_public(
    session: Session,
    *,
    raw_token: str,
    decision: str,
    signer_name: str,
    comment: str,
    now: datetime | None = None,
) -> None:
    now = now or datetime.now(timezone.utc)
    if decision not in {"approved", "rejected"}:
        raise ValueError("decision")
    signer_name = signer_name.strip()
    comment = comment.strip()
    if not signer_name or not comment:
        raise ValueError("required")
    link = _link_by_token(session, raw_token)
    if link is None:
        raise PermissionError(PUBLIC_MISS)
    case = session.get(CporCase, link.case_id)
    if case is None or link_block(link, now=now, current_version=int(case.export_version)) is not None:
        raise PermissionError(PUBLIC_MISS)
    event = signoff_event(
        decision=decision,
        signer_name=signer_name,
        comment=comment,
        export_version=int(link.export_version),
        recipient_email=link.recipient_email,
        decided_at=now,
    )
    link.decided_at = now
    link.decision = decision
    link.signer_name = signer_name
    link.comment = comment
    session.add(
        CporCaseEvent(
            case_id=case.id,
            event_type=event["event_type"],
            actor=event["actor"],
            payload_json=event["payload"],
        )
    )


def issue_link(
    session: Session,
    *,
    case_id: int,
    recipient_email: str,
    actor: str,
    now: datetime | None = None,
    send=send_digest_email,
) -> dict[str, Any]:
    """Retire open links, store a new hash, and mail it. The return value has no token."""
    now = now or datetime.now(timezone.utc)
    email = recipient_email.strip().lower()
    case, _customer = load_case_customer(session, case_id)
    origin = get_settings().cip_public_web_origin.strip()
    if not origin:
        raise RuntimeError("public_origin")
    _revoke_open(session, case_id, now)
    raw = new_session_token()
    row = CporCaseApprovalLink(
        case_id=case.id,
        token_hash=hash_session_token(raw),
        export_version=int(case.export_version),
        recipient_email=email,
        expires_at=now + LINK_TTL,
        created_by=actor,
    )
    session.add(row)
    session.flush()
    link = approval_link(raw)
    subject, text, html = compose_approval_mail(link, case.case_code)
    try:
        send(to_addr=email, subject=subject, html_body=html, text_body=text)
    except Exception as exc:
        row.revoked_at = now
        logger.warning(
            "customer_approval send_failed case_id=%s error_type=%s",
            case.id,
            type(exc).__name__,
        )
        raise RuntimeError("send_failed") from exc
    session.add(
        CporCaseEvent(
            case_id=case.id,
            event_type="customer_approval_link_sent",
            actor=actor,
            payload_json={
                "recipient_email": email,
                "export_version": int(case.export_version),
                "expires_at": row.expires_at.isoformat(),
            },
        )
    )
    logger.info("customer_approval sent case_id=%s", case.id)
    return planner_view(row, now=now, current_version=int(case.export_version))


def revoke_open(session: Session, *, case_id: int, actor: str, now: datetime | None = None) -> dict[str, Any]:
    now = now or datetime.now(timezone.utc)
    case, _customer = load_case_customer(session, case_id)
    count = _revoke_open(session, case_id, now)
    if count:
        session.add(
            CporCaseEvent(
                case_id=case.id,
                event_type="customer_approval_link_revoked",
                actor=actor,
                payload_json={"revoked_count": count},
            )
        )
    return planner_view(_latest(session, case_id), now=now, current_version=int(case.export_version))


def status_for_planner(session: Session, case_id: int, now: datetime | None = None) -> dict[str, Any]:
    now = now or datetime.now(timezone.utc)
    case, _customer = load_case_customer(session, case_id)
    return planner_view(_latest(session, case_id), now=now, current_version=int(case.export_version))


def _link_by_token(session: Session, raw_token: str) -> CporCaseApprovalLink | None:
    token_hash = hash_session_token((raw_token or "").strip())
    return session.scalars(
        select(CporCaseApprovalLink).where(CporCaseApprovalLink.token_hash == token_hash)
    ).first()
