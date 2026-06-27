"""Approved customer source-token alias scope (migration 0048) — shared by map and provisional writers."""

from __future__ import annotations

from typing import Any

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from app.models.dimensions import DimCustomer
from app.models.import_distributor_si import CustomerSourceTokenAlias, ImportEntityMappingCandidate
from app.services.imports.dsi_steward_candidate_ops import (
    StewardOpError,
    _is_dsi_steward_terminal_status,
    _source_customer_alias_raw_for_dsi_candidate,
    dsi_customer_alias_normalized_token,
)


def customer_alias_scope_key(
    normalized_token: str,
    source_definition_id: int | None,
    distributor_id: int | None,
) -> tuple[str, int, int]:
    """Approved-alias unique scope per migration 0048 (COALESCE sentinels)."""
    return (
        normalized_token[:512],
        int(source_definition_id) if source_definition_id is not None else -1,
        int(distributor_id) if distributor_id is not None else -1,
    )


def scope_key_for_dsi_candidate(cand: ImportEntityMappingCandidate) -> tuple[tuple[str, int, int], str] | None:
    # The alias key is the candidate's resolution identity (dealer-group primary), NOT the
    # customer-name evidence — otherwise the resolver never finds the alias it just wrote.
    nt = dsi_customer_alias_normalized_token(cand)
    if not nt.strip():
        return None
    return customer_alias_scope_key(nt, cand.source_definition_id, None), nt


def lookup_approved_customer_alias_for_scope(
    session: Session,
    *,
    normalized_token: str,
    source_definition_id: int | None,
    distributor_id: int | None,
) -> CustomerSourceTokenAlias | None:
    scope_src = int(source_definition_id) if source_definition_id is not None else -1
    scope_dist = int(distributor_id) if distributor_id is not None else -1
    return session.scalars(
        select(CustomerSourceTokenAlias)
        .where(
            CustomerSourceTokenAlias.status == "approved",
            CustomerSourceTokenAlias.normalized_token == normalized_token[:512],
            func.coalesce(CustomerSourceTokenAlias.source_definition_id, -1) == scope_src,
            func.coalesce(CustomerSourceTokenAlias.distributor_id, -1) == scope_dist,
        )
        .limit(1)
    ).first()


async def lookup_approved_customer_alias_for_scope_async(
    db: AsyncSession,
    *,
    normalized_token: str,
    source_definition_id: int | None,
    distributor_id: int | None,
) -> CustomerSourceTokenAlias | None:
    scope_src = int(source_definition_id) if source_definition_id is not None else -1
    scope_dist = int(distributor_id) if distributor_id is not None else -1
    return (
        await db.scalars(
            select(CustomerSourceTokenAlias)
            .where(
                CustomerSourceTokenAlias.status == "approved",
                CustomerSourceTokenAlias.normalized_token == normalized_token[:512],
                func.coalesce(CustomerSourceTokenAlias.source_definition_id, -1) == scope_src,
                func.coalesce(CustomerSourceTokenAlias.distributor_id, -1) == scope_dist,
            )
            .limit(1)
        )
    ).first()


def load_approved_customer_aliases_for_scopes(
    session: Session,
    scope_keys: set[tuple[str, int, int]],
) -> dict[tuple[str, int, int], CustomerSourceTokenAlias]:
    if not scope_keys:
        return {}
    normalized_tokens = {k[0] for k in scope_keys}
    rows = session.scalars(
        select(CustomerSourceTokenAlias).where(
            CustomerSourceTokenAlias.status == "approved",
            CustomerSourceTokenAlias.normalized_token.in_(normalized_tokens),
        )
    ).all()
    out: dict[tuple[str, int, int], CustomerSourceTokenAlias] = {}
    for row in rows:
        key = customer_alias_scope_key(row.normalized_token, row.source_definition_id, row.distributor_id)
        if key in scope_keys and key not in out:
            out[key] = row
    return out


def _alias_insert_sql() -> str:
    return """
            INSERT INTO customer_source_token_alias (
                customer_id, source_definition_id, distributor_id,
                raw_token, normalized_token, dealer_group_token,
                status, notes, created_from_import_job_id,
                import_entity_mapping_candidate_id, created_at, updated_at
            )
            VALUES (
                :customer_id, :source_definition_id, :distributor_id,
                :raw_token, :normalized_token, :dealer_group_token,
                'approved', :notes, :created_from_import_job_id,
                :import_entity_mapping_candidate_id, NOW(), NOW()
            )
            ON CONFLICT DO NOTHING
            RETURNING id
            """


def _alias_insert_params(
    *,
    customer_id: int,
    raw_token: str,
    normalized_token: str,
    source_definition_id: int | None,
    distributor_id: int | None,
    dealer_group_token: str | None,
    notes: str,
    created_from_import_job_id: int,
    import_entity_mapping_candidate_id: int,
) -> dict[str, Any]:
    return {
        "customer_id": int(customer_id),
        "source_definition_id": source_definition_id,
        "distributor_id": distributor_id,
        "raw_token": raw_token[:512],
        "normalized_token": normalized_token[:512],
        "dealer_group_token": dealer_group_token[:512] if dealer_group_token else None,
        "notes": notes,
        "created_from_import_job_id": int(created_from_import_job_id),
        "import_entity_mapping_candidate_id": int(import_entity_mapping_candidate_id),
    }


def insert_approved_customer_alias_on_conflict_do_nothing(
    session: Session,
    *,
    customer_id: int,
    raw_token: str,
    normalized_token: str,
    source_definition_id: int | None,
    distributor_id: int | None,
    dealer_group_token: str | None,
    notes: str,
    created_from_import_job_id: int,
    import_entity_mapping_candidate_id: int,
) -> int | None:
    """Insert alias; return new id or None when uq_cust_src_token_alias_approved_scope blocks insert."""
    row = session.execute(
        text(_alias_insert_sql()),
        _alias_insert_params(
            customer_id=customer_id,
            raw_token=raw_token,
            normalized_token=normalized_token,
            source_definition_id=source_definition_id,
            distributor_id=distributor_id,
            dealer_group_token=dealer_group_token,
            notes=notes,
            created_from_import_job_id=created_from_import_job_id,
            import_entity_mapping_candidate_id=import_entity_mapping_candidate_id,
        ),
    ).first()
    if row is not None and row[0] is not None:
        return int(row[0])
    return None


async def insert_approved_customer_alias_on_conflict_do_nothing_async(
    db: AsyncSession,
    *,
    customer_id: int,
    raw_token: str,
    normalized_token: str,
    source_definition_id: int | None,
    distributor_id: int | None,
    dealer_group_token: str | None,
    notes: str,
    created_from_import_job_id: int,
    import_entity_mapping_candidate_id: int,
) -> int | None:
    row = (
        await db.execute(
            text(_alias_insert_sql()),
            _alias_insert_params(
                customer_id=customer_id,
                raw_token=raw_token,
                normalized_token=normalized_token,
                source_definition_id=source_definition_id,
                distributor_id=distributor_id,
                dealer_group_token=dealer_group_token,
                notes=notes,
                created_from_import_job_id=created_from_import_job_id,
                import_entity_mapping_candidate_id=import_entity_mapping_candidate_id,
            ),
        )
    ).first()
    if row is not None and row[0] is not None:
        return int(row[0])
    return None


def _alias_scope_customer_conflict(
    existing_customer_id: int,
    target_customer_id: int,
    *,
    normalized_token: str,
) -> StewardOpError:
    return StewardOpError(
        (
            f"Approved alias for normalized token {normalized_token!r} already maps to "
            f"customer_id {existing_customer_id}; plan targets customer_id {target_customer_id}"
        ),
        status_code=409,
    )


def bind_candidate_to_reused_customer(
    cand: ImportEntityMappingCandidate,
    customer: DimCustomer,
    *,
    alias_id: int | None,
    reuse_kind: str,
) -> dict[str, Any]:
    cand.status = "resolved"
    cand.suggested_entity_id = int(customer.id)
    cand.match_reason = "steward_reused_approved_customer_alias"
    return {
        "ok": True,
        "reused": True,
        "reuse_kind": reuse_kind,
        "customer_id": customer.id,
        "customer_code": customer.code,
        "alias_id": alias_id,
        "candidate_id": cand.id,
    }


def _bind_candidate_to_mapped_customer(
    cand: ImportEntityMappingCandidate,
    customer: DimCustomer,
    *,
    alias_id: int | None,
    reused: bool,
    reuse_kind: str | None = None,
) -> dict[str, Any]:
    cand.status = "resolved"
    cand.suggested_entity_id = int(customer.id)
    cand.match_reason = (
        "steward_reused_approved_customer_alias" if reused else "steward_map_existing_customer"
    )
    out: dict[str, Any] = {
        "ok": True,
        "customer_id": customer.id,
        "customer_code": customer.code,
        "alias_id": alias_id,
        "candidate_id": cand.id,
    }
    if reused:
        out["reused"] = True
        out["reuse_kind"] = reuse_kind or "existing_alias"
    return out


def apply_map_dsi_customer_scoped_sync(
    session: Session,
    cand: ImportEntityMappingCandidate,
    *,
    customer_id: int,
    raw_token: str | None,
    approved_alias_by_scope: dict[tuple[str, int, int], CustomerSourceTokenAlias],
    batch_scope_claimed: set[tuple[str, int, int]],
) -> dict[str, Any]:
    """Map one candidate to an existing customer respecting alias-scope uniqueness."""
    if cand.entity_type != "customer_dealer_token":
        raise StewardOpError("Not customer_dealer_token", status_code=400)
    if _is_dsi_steward_terminal_status(cand.status):
        raise StewardOpError("Candidate already terminal", status_code=400)
    cust = session.get(DimCustomer, int(customer_id))
    if not cust:
        raise StewardOpError("customer_id not found", status_code=400)
    raw = (raw_token or _source_customer_alias_raw_for_dsi_candidate(cand)).strip()
    if not raw:
        raise StewardOpError("raw_token required", status_code=400)
    scope_meta = scope_key_for_dsi_candidate(cand)
    if scope_meta is None:
        raise StewardOpError("raw_token empty after normalization", status_code=400)
    scope_key, nt = scope_meta

    existing_alias = approved_alias_by_scope.get(scope_key)
    if existing_alias is None:
        existing_alias = lookup_approved_customer_alias_for_scope(
            session,
            normalized_token=nt,
            source_definition_id=cand.source_definition_id,
            distributor_id=None,
        )
        if existing_alias is not None:
            approved_alias_by_scope[scope_key] = existing_alias

    if existing_alias is not None:
        if int(existing_alias.customer_id) != int(customer_id):
            raise _alias_scope_customer_conflict(
                int(existing_alias.customer_id), int(customer_id), normalized_token=nt
            )
        keeper = session.get(DimCustomer, int(existing_alias.customer_id))
        if keeper is None:
            raise StewardOpError("Approved alias points at missing customer", status_code=409)
        return _bind_candidate_to_mapped_customer(
            cand,
            keeper,
            alias_id=int(existing_alias.id),
            reused=True,
            reuse_kind="existing_alias",
        )

    if scope_key in batch_scope_claimed:
        return _bind_candidate_to_mapped_customer(
            cand,
            cust,
            alias_id=None,
            reused=True,
            reuse_kind="batch",
        )

    notes = f"Mapped from import candidate {cand.id} (job {cand.import_job_id})"
    alias_id = insert_approved_customer_alias_on_conflict_do_nothing(
        session,
        customer_id=int(customer_id),
        raw_token=raw,
        normalized_token=nt,
        source_definition_id=cand.source_definition_id,
        distributor_id=None,
        dealer_group_token=cand.dealer_group_token,
        notes=notes,
        created_from_import_job_id=cand.import_job_id,
        import_entity_mapping_candidate_id=cand.id,
    )
    batch_scope_claimed.add(scope_key)

    if alias_id is None:
        race_alias = lookup_approved_customer_alias_for_scope(
            session,
            normalized_token=nt,
            source_definition_id=cand.source_definition_id,
            distributor_id=None,
        )
        if race_alias is None:
            raise StewardOpError("Could not create or reuse customer alias for scope", status_code=409)
        approved_alias_by_scope[scope_key] = race_alias
        if int(race_alias.customer_id) != int(customer_id):
            raise _alias_scope_customer_conflict(
                int(race_alias.customer_id), int(customer_id), normalized_token=nt
            )
        keeper = session.get(DimCustomer, int(race_alias.customer_id))
        if keeper is None:
            raise StewardOpError("Approved alias points at missing customer", status_code=409)
        return _bind_candidate_to_mapped_customer(
            cand,
            keeper,
            alias_id=int(race_alias.id),
            reused=True,
            reuse_kind="race",
        )

    alias_row = session.get(CustomerSourceTokenAlias, alias_id)
    if alias_row is not None:
        approved_alias_by_scope[scope_key] = alias_row
    return _bind_candidate_to_mapped_customer(
        cand,
        cust,
        alias_id=alias_id,
        reused=False,
    )


async def apply_map_dsi_customer_scoped_async(
    db: AsyncSession,
    cand: ImportEntityMappingCandidate,
    *,
    customer_id: int,
    raw_token: str | None,
) -> dict[str, Any]:
    """Single-row map (async session) with the same alias-scope contract as bulk map."""
    if cand.entity_type != "customer_dealer_token":
        raise StewardOpError("Not customer_dealer_token", status_code=400)
    if _is_dsi_steward_terminal_status(cand.status):
        raise StewardOpError("Candidate already terminal", status_code=400)
    cust = await db.get(DimCustomer, int(customer_id))
    if not cust:
        raise StewardOpError("customer_id not found", status_code=400)
    raw = (raw_token or _source_customer_alias_raw_for_dsi_candidate(cand)).strip()
    if not raw:
        raise StewardOpError("raw_token required", status_code=400)
    scope_meta = scope_key_for_dsi_candidate(cand)
    if scope_meta is None:
        raise StewardOpError("raw_token empty after normalization", status_code=400)
    scope_key, nt = scope_meta

    existing_alias = await lookup_approved_customer_alias_for_scope_async(
        db,
        normalized_token=nt,
        source_definition_id=cand.source_definition_id,
        distributor_id=None,
    )
    if existing_alias is not None:
        if int(existing_alias.customer_id) != int(customer_id):
            raise _alias_scope_customer_conflict(
                int(existing_alias.customer_id), int(customer_id), normalized_token=nt
            )
        keeper = await db.get(DimCustomer, int(existing_alias.customer_id))
        if keeper is None:
            raise StewardOpError("Approved alias points at missing customer", status_code=409)
        return _bind_candidate_to_mapped_customer(
            cand,
            keeper,
            alias_id=int(existing_alias.id),
            reused=True,
            reuse_kind="existing_alias",
        )

    notes = f"Mapped from import candidate {cand.id} (job {cand.import_job_id})"
    alias_id = await insert_approved_customer_alias_on_conflict_do_nothing_async(
        db,
        customer_id=int(customer_id),
        raw_token=raw,
        normalized_token=nt,
        source_definition_id=cand.source_definition_id,
        distributor_id=None,
        dealer_group_token=cand.dealer_group_token,
        notes=notes,
        created_from_import_job_id=cand.import_job_id,
        import_entity_mapping_candidate_id=cand.id,
    )
    if alias_id is None:
        race_alias = await lookup_approved_customer_alias_for_scope_async(
            db,
            normalized_token=nt,
            source_definition_id=cand.source_definition_id,
            distributor_id=None,
        )
        if race_alias is None:
            raise StewardOpError("Could not create or reuse customer alias for scope", status_code=409)
        if int(race_alias.customer_id) != int(customer_id):
            raise _alias_scope_customer_conflict(
                int(race_alias.customer_id), int(customer_id), normalized_token=nt
            )
        keeper = await db.get(DimCustomer, int(race_alias.customer_id))
        if keeper is None:
            raise StewardOpError("Approved alias points at missing customer", status_code=409)
        return _bind_candidate_to_mapped_customer(
            cand,
            keeper,
            alias_id=int(race_alias.id),
            reused=True,
            reuse_kind="race",
        )

    return _bind_candidate_to_mapped_customer(
        cand,
        cust,
        alias_id=alias_id,
        reused=False,
    )
