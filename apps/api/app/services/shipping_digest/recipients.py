"""Intended shipping-digest recipients (locked five unless env override)."""

from __future__ import annotations

DEFAULT_SHIPPING_MAILER_RECIPIENTS: tuple[str, ...] = (
    "Leigh_Sharpe@asus.com",
    "Wayne_Holt@asus.com",
    "Kyle_Chung@asus.com",
    "Theshan_Naidoo@asus.com",
    "Warren_Eliason@asus.com",
)


def intended_mailer_recipients() -> tuple[str, ...]:
    from app.services.shipping_digest.config import mailer_recipients

    return mailer_recipients()
