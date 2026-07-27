"""Stable numeric surrogate id for (import_job, entity, token) pairs (Unit C, D-014).

Bookkeeping only — never a dimension, never resolution truth. The steward workspace and
resolution-plan engine need a stable integer id per unresolved token to use as a row key /
plan candidate id (replacing the client-side hash ``cporTokenRowId``). Get-or-create is
race-safe via a SAVEPOINT (``begin_nested``): a concurrent insert on the same
``(import_job_id, entity, token)`` triggers the unique constraint, and the losing caller
re-reads the winning row instead of failing the whole session.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.cpor_historical import ImportCporHistoricalTokenSurrogate

_VALID_ENTITIES = ("product", "customer", "distributor")


def _normalize(entity: str, token: str) -> tuple[str, str]:
    entity_norm = (entity or "").strip().lower()
    if entity_norm not in _VALID_ENTITIES:
        raise ValueError(f"unsupported entity: {entity!r}")
    token_val = str(token if token is not None else "").strip()[:256]
    return entity_norm, token_val


def _select_surrogate_id(db: Session, *, job_id: int, entity: str, token: str) -> int | None:
    return db.scalar(
        select(ImportCporHistoricalTokenSurrogate.id).where(
            ImportCporHistoricalTokenSurrogate.import_job_id == job_id,
            ImportCporHistoricalTokenSurrogate.entity == entity,
            ImportCporHistoricalTokenSurrogate.token == token,
        )
    )


def get_or_create_token_surrogate(db: Session, *, job_id: int, entity: str, token: str) -> int:
    """Return the stable surrogate id for ``(job_id, entity, token)``, creating it if absent.

    Caller owns commit — this only flushes within a nested SAVEPOINT so a unique-constraint
    race does not roll back unrelated work already pending on ``db``.
    """
    entity_norm, token_val = _normalize(entity, token)

    existing_id = _select_surrogate_id(db, job_id=job_id, entity=entity_norm, token=token_val)
    if existing_id is not None:
        return int(existing_id)

    row = ImportCporHistoricalTokenSurrogate(import_job_id=job_id, entity=entity_norm, token=token_val)
    try:
        with db.begin_nested():
            db.add(row)
            db.flush()
        return int(row.id)
    except IntegrityError:
        existing_id = _select_surrogate_id(db, job_id=job_id, entity=entity_norm, token=token_val)
        if existing_id is not None:
            return int(existing_id)
        raise
