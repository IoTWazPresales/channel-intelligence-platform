"""Approved ``CustomerSourceTokenAlias`` resolution for lineup customer tokens.

Mirrors the alias preload in ``shipment_evidence_resolution_plan.build_shipment_enrich_refs`` —
same columns, same ``_norm_key`` normalizer — without source-scoped guessing.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from app.models.commercial_lineup import CommercialLineupLine
from app.models.dimensions import DimCustomer
from app.models.import_distributor_si import CustomerSourceTokenAlias
from app.services.imports.distributor_sales_inventory import _norm_key
from app.services.imports.shipment_evidence_resolution_plan import (
    build_unique_approved_customer_alias_id_by_token,
)

# Tokens with approved aliases identified on cip before lineup alias wiring (IC gap audit).
KNOWN_FIXABLE_LINEUP_CUSTOMER_TOKENS: tuple[str, ...] = (
    "ic",
    "lewis",
    "sadc - tbh",
    "sample",
    "syntech",
)


def load_approved_customer_alias_id_by_token_sync(db: Session) -> dict[str, int]:
    """Load approved customer aliases once (sync), keyed by ``normalized_token``."""
    rows = list(
        db.execute(
            select(
                CustomerSourceTokenAlias.normalized_token,
                CustomerSourceTokenAlias.customer_id,
                CustomerSourceTokenAlias.source_definition_id,
            ).where(CustomerSourceTokenAlias.status == "approved")
        ).all()
    )
    return build_unique_approved_customer_alias_id_by_token(rows)


async def load_approved_customer_alias_id_by_token_async(db: AsyncSession) -> dict[str, int]:
    """Load approved customer aliases once (async), keyed by ``normalized_token``."""
    rows = list(
        (
            await db.execute(
                select(
                    CustomerSourceTokenAlias.normalized_token,
                    CustomerSourceTokenAlias.customer_id,
                    CustomerSourceTokenAlias.source_definition_id,
                ).where(CustomerSourceTokenAlias.status == "approved")
            )
        ).all()
    )
    return build_unique_approved_customer_alias_id_by_token(rows)


def resolve_lineup_customer_id_from_token(
    customer_token: str | None,
    *,
    customer_map: dict[str, DimCustomer],
    customer_alias_map: dict[str, int],
    customers_by_id: dict[int, DimCustomer],
) -> int | None:
    """Resolve lineup ``customer_token`` via dim name/code, then unique approved alias."""
    token = (customer_token or "").strip()
    if not token:
        return None
    direct = customer_map.get(token.lower())
    if direct is not None:
        return int(direct.id)
    norm = _norm_key(token)
    if not norm:
        return None
    alias_cid = customer_alias_map.get(norm)
    if alias_cid is None:
        return None
    hit = customers_by_id.get(int(alias_cid))
    return int(hit.id) if hit is not None else int(alias_cid)


def backfill_lineup_customer_aliases_sync(
    db: Session,
    *,
    tokens: tuple[str, ...] | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Set ``commercial_lineup_line.customer_id`` from approved aliases where still null."""
    alias_map = load_approved_customer_alias_id_by_token_sync(db)
    norm_tokens = {_norm_key(t) for t in (tokens or KNOWN_FIXABLE_LINEUP_CUSTOMER_TOKENS)}
    norm_tokens.discard("")

    lines = list(
        db.scalars(
            select(CommercialLineupLine).where(
                CommercialLineupLine.customer_id.is_(None),
                CommercialLineupLine.customer_token.isnot(None),
            )
        ).all()
    )

    before_unresolved = 0
    after_would_resolve = 0
    updates: list[tuple[int, int, str]] = []
    per_token_before: dict[str, int] = {}
    per_token_after: dict[str, int] = {}

    for ln in lines:
        raw_tok = (ln.customer_token or "").strip()
        if not raw_tok:
            continue
        norm = _norm_key(raw_tok)
        if norm not in norm_tokens:
            continue
        before_unresolved += 1
        per_token_before[norm] = per_token_before.get(norm, 0) + 1
        cid = alias_map.get(norm)
        if cid is None:
            continue
        after_would_resolve += 1
        per_token_after[norm] = per_token_after.get(norm, 0) + 1
        updates.append((int(ln.id), int(cid), norm))
        if not dry_run:
            ln.customer_id = int(cid)
            diag = list(ln.diagnostic_codes or [])
            if "unknown_customer" in diag:
                diag = [d for d in diag if d != "unknown_customer"]
                ln.diagnostic_codes = diag or None

    if not dry_run and updates:
        db.commit()

    return {
        "dry_run": dry_run,
        "tokens": sorted(norm_tokens),
        "lines_scanned": len(lines),
        "before_unresolved_in_scope": before_unresolved,
        "after_resolved_in_scope": after_would_resolve,
        "per_token_before": per_token_before,
        "per_token_after": per_token_after,
        "updates_applied": 0 if dry_run else len(updates),
        "sample_updates": updates[:10],
    }
