"""Optional email delivery for promo exports (disabled by default)."""

from __future__ import annotations

from app.core.config import get_settings


def maybe_send_export_email(*, export_id: int, to_address: str | None, storage_key: str) -> dict:
    """Stub hook: returns a payload describing what would be sent. SMTP wiring is intentionally out of scope for MVP."""
    settings = get_settings()
    if not settings.promo_export_email_enabled:
        return {"queued": False, "reason": "promo_export_email_enabled is false"}
    if not to_address:
        return {"queued": False, "reason": "missing recipient"}
    return {
        "queued": False,
        "reason": "SMTP adapter not configured; use manual download",
        "export_id": export_id,
        "to": to_address,
        "storage_key": storage_key,
    }
