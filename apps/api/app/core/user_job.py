"""A user's job (N-0100 part B, D-0133 / D-0138). A job is not a role.

The five jobs are account manager, product manager, finance, country manager and admin. The job
is stored on ``app_user.job``, separate from ``role``. Permission checks keep using the role; the
job never changes what ``require_roles`` allows. A user can have a role and no job.
"""

from __future__ import annotations

JOBS: tuple[str, ...] = ("account_manager", "product_manager", "finance", "country_manager", "admin")


def normalize_job(value: object) -> str | None:
    """``None`` or blank is no job; otherwise one of ``JOBS`` (case and spaces folded)."""
    if value is None:
        return None
    text = str(value).strip().lower().replace(" ", "_").replace("-", "_")
    if text == "":
        return None
    if text not in JOBS:
        raise ValueError("Job is account_manager, product_manager, finance, country_manager, admin, or empty.")
    return text
