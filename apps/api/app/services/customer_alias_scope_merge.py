"""Steward-governed merge for approved customer alias-scope conflicts."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func, select, text, update
from sqlalchemy.orm import Session

from app.models.dimensions import DimCustomer
from app.models.import_distributor_si import CustomerSourceTokenAlias
from app.services.commercial_planner.open_channel_customer import OPEN_CHANNEL_CUSTOMER_CODE
from app.services.customer_alias_scope_grouping import (
    canonical_customer_alias_token,
    customer_ids_for_canonical_scope_conflict,
    scope_bucket_ids,
)
from app.services.customer_duplicate_groups import _CustomerRow, survivor_hint_sort_key
from app.services.customer_usage import _SPECS
from app.services.imports.provisional_entity_consolidation import repoint_customer_id_references_full


class CustomerAliasScopeMergeError(ValueError):
    pass


def _approved_alias_rows_in_scope(
    db: Session,
    *,
    source_definition_id: int | None,
    distributor_id: int | None,
) -> list[tuple[str, int, int | None, int | None]]:
    scope_src, scope_dist = scope_bucket_ids(source_definition_id, distributor_id)
    rows = db.execute(
        text(
            """
            SELECT normalized_token, customer_id, source_definition_id, distributor_id
            FROM customer_source_token_alias
            WHERE status = 'approved'
              AND COALESCE(source_definition_id, -1) = :scope_src
              AND COALESCE(distributor_id, -1) = :scope_dist
            """
        ),
        {"scope_src": scope_src, "scope_dist": scope_dist},
    ).fetchall()
    return [(str(r[0]), int(r[1]), r[2], r[3]) for r in rows]


def _load_scope_conflict_customer_ids(
    db: Session,
    *,
    normalized_token: str,
    source_definition_id: int | None,
    distributor_id: int | None,
) -> list[int]:
    rows = _approved_alias_rows_in_scope(
        db,
        source_definition_id=source_definition_id,
        distributor_id=distributor_id,
    )
    return customer_ids_for_canonical_scope_conflict(
        rows,
        normalized_token=normalized_token,
        source_definition_id=source_definition_id,
        distributor_id=distributor_id,
    )


def _customer_rows_for_ids(db: Session, customer_ids: list[int]) -> list[_CustomerRow]:
    if not customer_ids:
        return []
    rows = db.execute(
        select(
            DimCustomer.id,
            DimCustomer.code,
            DimCustomer.name,
            DimCustomer.customer_status,
            DimCustomer.created_at,
        ).where(DimCustomer.id.in_(customer_ids))
    ).all()
    return [
        _CustomerRow(
            id=int(r.id),
            code=str(r.code),
            name=str(r.name),
            customer_status=str(r.customer_status or ""),
            created_at=r.created_at,
        )
        for r in rows
    ]


def _default_survivor_id(db: Session, customer_ids: list[int]) -> int:
    members = _customer_rows_for_ids(db, customer_ids)
    if not members:
        raise CustomerAliasScopeMergeError("No customers found for scope")
    return sorted(members, key=survivor_hint_sort_key)[0].id


def _assert_survivor_valid(
    db: Session,
    *,
    survivor_id: int,
    customer_ids: list[int],
) -> DimCustomer:
    if int(survivor_id) not in customer_ids:
        raise CustomerAliasScopeMergeError(
            f"survivor_id {survivor_id} is not a member of this alias-scope conflict group"
        )
    survivor = db.get(DimCustomer, int(survivor_id))
    if survivor is None:
        raise CustomerAliasScopeMergeError(f"survivor_id {survivor_id} not found")
    if survivor.code == OPEN_CHANNEL_CUSTOMER_CODE:
        raise CustomerAliasScopeMergeError("OPEN_CHANNEL cannot be a merge survivor")
    return survivor


def _fk_breakdown_sync(db: Session, customer_id: int) -> list[dict[str, int | str]]:
    from app.services.master_usage_batch import batch_counts_multi_table_sync, count_subquery_for_columns

    ids = [int(customer_id)]
    subqueries = [count_subquery_for_columns(label, [col], ids) for label, col in _SPECS]
    batch = batch_counts_multi_table_sync(db, subqueries, ids)
    return sorted(batch.get(customer_id, []), key=lambda r: str(r.get("label", "")))


def preview_customer_alias_scope_merge(
    db: Session,
    *,
    normalized_token: str,
    source_definition_id: int | None,
    distributor_id: int | None,
    survivor_id: int | None,
    audit_note: str,
) -> dict[str, Any]:
    note = (audit_note or "").strip()
    if not note:
        raise CustomerAliasScopeMergeError("audit_note is required")

    customer_ids = _load_scope_conflict_customer_ids(
        db,
        normalized_token=normalized_token,
        source_definition_id=source_definition_id,
        distributor_id=distributor_id,
    )
    if len(customer_ids) < 2:
        raise CustomerAliasScopeMergeError("No alias-scope conflict found for this scope")

    kid = int(survivor_id) if survivor_id is not None else _default_survivor_id(db, customer_ids)
    _assert_survivor_valid(db, survivor_id=kid, customer_ids=customer_ids)
    losers = [int(x) for x in customer_ids if int(x) != kid]

    loser_plans: list[dict[str, Any]] = []
    for lid in losers:
        loser_plans.append(
            {
                "customer_id": lid,
                "fk_breakdown": _fk_breakdown_sync(db, lid),
                "action": "repoint_and_soft_redirect",
            }
        )

    return {
        "dry_run": True,
        "scope": {
            "normalized_token": canonical_customer_alias_token(normalized_token)[:512],
            "source_definition_id": source_definition_id,
            "distributor_id": distributor_id,
        },
        "survivor_id": kid,
        "loser_ids": losers,
        "loser_plans": loser_plans,
        "audit_note": note,
    }


def _repoint_aliases_in_scope(
    db: Session,
    *,
    normalized_token: str,
    source_definition_id: int | None,
    distributor_id: int | None,
    survivor_id: int,
    loser_id: int,
) -> int:
    lookup = canonical_customer_alias_token(normalized_token)
    if not lookup:
        return 0
    scope_src, scope_dist = scope_bucket_ids(source_definition_id, distributor_id)
    aliases = list(
        db.scalars(
            select(CustomerSourceTokenAlias).where(
                CustomerSourceTokenAlias.status == "approved",
                CustomerSourceTokenAlias.customer_id == int(loser_id),
                func.coalesce(CustomerSourceTokenAlias.source_definition_id, -1) == scope_src,
                func.coalesce(CustomerSourceTokenAlias.distributor_id, -1) == scope_dist,
            )
        ).all()
    )
    ops = 0
    for al in aliases:
        if canonical_customer_alias_token(al.normalized_token) != lookup:
            continue
        dup = db.scalars(
            select(CustomerSourceTokenAlias)
            .where(
                CustomerSourceTokenAlias.customer_id == int(survivor_id),
                CustomerSourceTokenAlias.normalized_token == al.normalized_token,
                CustomerSourceTokenAlias.raw_token == al.raw_token,
            )
            .limit(1)
        ).first()
        if dup is not None:
            db.delete(al)
        else:
            al.customer_id = int(survivor_id)
            db.add(al)
        ops += 1
    return ops


def confirm_customer_alias_scope_merge_sync(
    db: Session,
    *,
    normalized_token: str,
    source_definition_id: int | None,
    distributor_id: int | None,
    survivor_id: int,
    audit_note: str,
    performed_by: str | None = None,
) -> dict[str, Any]:
    preview = preview_customer_alias_scope_merge(
        db,
        normalized_token=normalized_token,
        source_definition_id=source_definition_id,
        distributor_id=distributor_id,
        survivor_id=survivor_id,
        audit_note=audit_note,
    )
    kid = int(preview["survivor_id"])
    losers = [int(x) for x in preview["loser_ids"]]
    survivor = db.get(DimCustomer, kid)
    if survivor is None:
        raise CustomerAliasScopeMergeError("Survivor missing at apply time")

    stamp = datetime.now(timezone.utc).isoformat()
    actor = (performed_by or "steward").strip() or "steward"
    merge_line = (
        f"[alias-scope merge {stamp}] survivor={kid}; losers={losers}; by={actor}; note={audit_note.strip()[:400]}"
    )
    prior = (survivor.notes_summary or "").strip()
    survivor.notes_summary = f"{prior}\n{merge_line}".strip()[:512]
    db.add(survivor)

    repointed_alias_ops = 0
    repointed_fk_tables = 0
    soft_redirected: list[int] = []

    for lid in losers:
        repointed_alias_ops += _repoint_aliases_in_scope(
            db,
            normalized_token=normalized_token,
            source_definition_id=source_definition_id,
            distributor_id=distributor_id,
            survivor_id=kid,
            loser_id=lid,
        )
        repointed_fk_tables += repoint_customer_id_references_full(db, loser_id=lid, keeper_id=kid)

        loser_row = db.get(DimCustomer, lid)
        if loser_row is not None:
            loser_row.merged_into_customer_id = kid
            if loser_row.customer_status not in ("merged", "inactive"):
                loser_row.customer_status = "merged"
            db.add(loser_row)
            soft_redirected.append(lid)
        db.flush()

    db.commit()
    return {
        "dry_run": False,
        "scope": preview["scope"],
        "survivor_id": kid,
        "loser_ids": losers,
        "repointed_alias_ops": repointed_alias_ops,
        "repointed_fk_table_updates": repointed_fk_tables,
        "soft_redirected_customer_ids": soft_redirected,
        "audit_note": audit_note.strip(),
    }
