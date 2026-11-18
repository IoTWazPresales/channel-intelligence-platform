"""Seed addresses for an empty shipping-mailer recipient table.

There is no built-in address list: a tenant's first recipients come from
``CIP_SHIPPING_MAILER_RECIPIENTS`` (comma-separated) or are added in the UI.
"""

from __future__ import annotations

# Empty on purpose: recipients are tenant data (env seed or the admin UI), never code.
DEFAULT_SHIPPING_MAILER_RECIPIENTS: tuple[str, ...] = ()


def intended_mailer_recipients() -> tuple[str, ...]:
    """Seed source (env, else none). Live send list is ``resolve_shipping_recipients``."""
    from app.services.shipping_digest.config import mailer_recipients

    return mailer_recipients()
