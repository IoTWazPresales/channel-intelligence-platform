"""Past customer merges and changing which record is the keeper (N-0095).

A full merge keeps one record (the keeper) and points the others at it with
``merged_into_customer_id``. Every row that referenced a merged record now references the keeper,
so nothing records which rows came from which side before the merge.

Changing the keeper makes a merged record the live one again and merges the current keeper into
it: every row moves across, the old keeper's other merged records are redirected to the new keeper,
and the old keeper's name is sealed as an alias to the new keeper. The new keeper keeps its own
code and name. The steward chooses; nothing here picks a keeper.

Test-fixture customers are left out of the list (and counted). OPEN_CHANNEL always stays the keeper.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from app.models.dimensions import DimCustomer
from app.models.import_distributor_si import CustomerSourceTokenAlias
from app.services.commercial_planner.open_channel_customer import OPEN_CHANNEL_CUSTOMER_CODE
from app.services.customer_duplicate_groups import customer_fk_reference_counts_batch, paginate_groups
from app.services.customer_test_fixtures import is_test_fixture_customer
from app.services.merge_redirect import build_redirect_map

logger = logging.getLogger(__name__)

_MERGE_LINE_RE = re.compile(r"\[customer-full merge (?P<at>[^\]]+)\][^\n]*?losers=\[(?P<losers>[^\]]*)\]")
_ALIAS_SAMPLE = 12


class CustomerKeeperChangeError(ValueError):
    pass


def _is_open_channel(row: DimCustomer | None) -> bool:
    return row is not None and str(row.code or "").strip().upper() == OPEN_CHANNEL_CUSTOMER_CODE


def merged_at_from_keeper_notes(notes: str | None, loser_id: int) -> str | None:
    """Merge time written into the keeper's notes by the full merge, when still there."""
    for m in _MERGE_LINE_RE.finditer(notes or ""):
        ids = {x.strip() for x in m.group("losers").split(",")}
        if str(int(loser_id)) in ids:
            return m.group("at").strip()
    return None


def _origin(notes: str | None) -> str | None:
    first = (notes or "").strip().splitlines()
    return first[0][:240] if first else None


async def _evidence_by_customer(db: AsyncSession, ids: list[int]) -> dict[int, dict[str, Any]]:
    """Rows, sell-through, cases and aliases now held by each record."""
    from app.models.cpor import CporCase
    from app.models.fact_customer_sellthrough import FactCustomerSellthrough

    out: dict[int, dict[str, Any]] = {
        i: {"reference_rows": 0, "reference_counts": [], "sellthrough_rows": 0, "sellthrough_units": 0,
            "cases": 0, "alias_count": 0, "aliases": []}
        for i in ids
    }
    if not ids:
        return out
    refs = await customer_fk_reference_counts_batch(db, ids)
    for cid, counts in refs.items():
        out[cid]["reference_counts"] = sorted(counts, key=lambda r: str(r.get("label", "")))
        out[cid]["reference_rows"] = sum(int(r.get("count") or 0) for r in counts)
    st = await db.execute(
        select(
            FactCustomerSellthrough.customer_id,
            func.count(),
            func.coalesce(func.sum(FactCustomerSellthrough.units_sold), 0),
        )
        .where(FactCustomerSellthrough.customer_id.in_(ids))
        .group_by(FactCustomerSellthrough.customer_id)
    )
    for cid, n, units in st.all():
        out[int(cid)]["sellthrough_rows"] = int(n)
        out[int(cid)]["sellthrough_units"] = float(units or 0)
    cases = await db.execute(
        select(CporCase.customer_id, func.count()).where(CporCase.customer_id.in_(ids)).group_by(CporCase.customer_id)
    )
    for cid, n in cases.all():
        out[int(cid)]["cases"] = int(n)
    aliases = await db.execute(
        select(CustomerSourceTokenAlias.customer_id, CustomerSourceTokenAlias.raw_token)
        .where(CustomerSourceTokenAlias.customer_id.in_(ids), CustomerSourceTokenAlias.status == "approved")
        .order_by(CustomerSourceTokenAlias.customer_id, CustomerSourceTokenAlias.id)
    )
    for cid, raw in aliases.all():
        rec = out[int(cid)]
        rec["alias_count"] += 1
        if len(rec["aliases"]) < _ALIAS_SAMPLE and raw not in rec["aliases"]:
            rec["aliases"].append(raw)
    return out


def _record(row: Any, evidence: dict[str, Any], *, merged_at: str | None = None) -> dict[str, Any]:
    return {
        "id": int(row.id),
        "customer_code": row.code,
        "customer_name": row.name,
        "customer_status": row.customer_status,
        "created_at": row.created_at.isoformat() if row.created_at is not None else None,
        "origin": _origin(row.notes_summary),
        "merged_into_customer_id": row.merged_into_customer_id,
        "merged_at": merged_at,
        **evidence,
    }


async def list_past_merges(
    db: AsyncSession,
    *,
    page: int = 1,
    page_size: int = 25,
    q: str | None = None,
) -> dict[str, Any]:
    """Keepers that have merged records, each with the evidence now on every record."""
    rows = (
        await db.execute(
            select(
                DimCustomer.id,
                DimCustomer.code,
                DimCustomer.name,
                DimCustomer.customer_status,
                DimCustomer.created_at,
                DimCustomer.notes_summary,
                DimCustomer.merged_into_customer_id,
            )
        )
    ).all()
    by_id = {int(r.id): r for r in rows}
    redirect = build_redirect_map((int(r.id), r.merged_into_customer_id) for r in rows)

    groups_by_keeper: dict[int, list[int]] = {}
    fixtures = 0
    for r in rows:
        if r.merged_into_customer_id is None:
            continue
        kid = redirect.get(int(r.id), int(r.id))
        keeper = by_id.get(kid)
        if keeper is None or kid == int(r.id):
            continue
        if is_test_fixture_customer(r.code, r.name) or is_test_fixture_customer(keeper.code, keeper.name):
            fixtures += 1
            continue
        groups_by_keeper.setdefault(kid, []).append(int(r.id))

    needle = (q or "").strip().lower()
    groups: list[dict[str, Any]] = []
    for kid, loser_ids in groups_by_keeper.items():
        members = [by_id[kid], *(by_id[i] for i in loser_ids)]
        if needle and not any(needle in f"{m.name} {m.code}".lower() for m in members):
            continue
        groups.append({"keeper_id": kid, "loser_ids": sorted(loser_ids), "sort": str(by_id[kid].name).lower()})
    groups.sort(key=lambda g: (g["sort"], g["keeper_id"]))
    page_groups, total = paginate_groups(groups, page, page_size)

    ids = [i for g in page_groups for i in (g["keeper_id"], *g["loser_ids"])]
    evidence = await _evidence_by_customer(db, ids)
    items = []
    for g in page_groups:
        keeper = by_id[g["keeper_id"]]
        items.append(
            {
                "keeper": _record(keeper, evidence[g["keeper_id"]]),
                "merged": [
                    _record(
                        by_id[i],
                        evidence[i],
                        merged_at=merged_at_from_keeper_notes(keeper.notes_summary, i),
                    )
                    for i in g["loser_ids"]
                ],
            }
        )
    return {
        "items": items,
        "page": page,
        "page_size": page_size,
        "total": total,
        "test_fixture_merges_excluded": fixtures,
        "note": "Rows moved to the keeper at merge time; which rows came from which record was not recorded.",
    }


def _validate(
    db: Session,
    *,
    current_keeper_id: int,
    new_keeper_id: int,
    allow_open_channel_keeper: bool,
) -> tuple[DimCustomer, DimCustomer]:
    cur = db.get(DimCustomer, int(current_keeper_id))
    new = db.get(DimCustomer, int(new_keeper_id))
    if cur is None or new is None:
        raise CustomerKeeperChangeError("Customer not found")
    if cur.merged_into_customer_id is not None:
        raise CustomerKeeperChangeError(f"Customer {cur.id} is not a keeper: it is merged into {cur.merged_into_customer_id}")
    if new.merged_into_customer_id is None or int(new.merged_into_customer_id) != int(cur.id):
        raise CustomerKeeperChangeError(f"Customer {new.id} is not merged into {cur.id}")
    if _is_open_channel(cur):
        raise CustomerKeeperChangeError("OPEN_CHANNEL stays the keeper")
    if _is_open_channel(new) and not allow_open_channel_keeper:
        raise CustomerKeeperChangeError("OPEN_CHANNEL can only be restored as keeper by the repair script")
    return cur, new


def preview_change_keeper(
    db: Session,
    *,
    current_keeper_id: int,
    new_keeper_id: int,
    audit_note: str,
    allow_open_channel_keeper: bool = False,
) -> dict[str, Any]:
    from app.services.customer_full_repoint import count_customer_fk_refs
    from app.services.customer_merge_alias_seal import seal_loser_display_name_aliases

    note = (audit_note or "").strip()
    if not note:
        raise CustomerKeeperChangeError("audit_note is required")
    cur, new = _validate(
        db,
        current_keeper_id=current_keeper_id,
        new_keeper_id=new_keeper_id,
        allow_open_channel_keeper=allow_open_channel_keeper,
    )
    moving = count_customer_fk_refs(db, int(cur.id))
    other_merged = [
        int(x)
        for x in db.scalars(
            select(DimCustomer.id).where(
                DimCustomer.merged_into_customer_id == int(cur.id), DimCustomer.id != int(new.id)
            )
        ).all()
    ]
    seal_plan = seal_loser_display_name_aliases(
        db, keeper_id=int(new.id), loser_ids=[int(cur.id)], audit_note=note, dry_run=True
    )
    db.rollback()
    return {
        "dry_run": True,
        "current_keeper": {"id": int(cur.id), "code": cur.code, "name": cur.name, "status": cur.customer_status},
        "new_keeper": {"id": int(new.id), "code": new.code, "name": new.name, "status": new.customer_status},
        "new_keeper_status_after": _status_after(cur),
        "rows_to_move": sum(v for k, v in moving.items() if k != "dim_customer.merged_into_customer_id"),
        "rows_to_move_by_table": {k: v for k, v in sorted(moving.items()) if k != "dim_customer.merged_into_customer_id"},
        "rows_already_on_new_keeper": sum(count_customer_fk_refs(db, int(new.id)).values()),
        "other_merged_records_redirected": other_merged,
        "alias_seal_plan": seal_plan,
        "kept": f"{new.code} — {new.name} keeps its code and name; {cur.code} — {cur.name} becomes a merged record.",
        "audit_note": note,
    }


def _status_after(cur: DimCustomer) -> str:
    status = str(cur.customer_status or "").strip().lower()
    return status if status and status not in ("merged", "inactive") else "active"


def confirm_change_keeper(
    db: Session,
    *,
    current_keeper_id: int,
    new_keeper_id: int,
    audit_note: str,
    performed_by: str | None = None,
    allow_open_channel_keeper: bool = False,
) -> dict[str, Any]:
    """Make ``new_keeper_id`` the keeper and merge ``current_keeper_id`` into it. One transaction."""
    from app.services.customer_full_repoint import (
        CustomerFullRepointAbortError,
        count_customer_fk_refs,
        repoint_customer_footprint_full,
    )
    from app.services.customer_merge_alias_seal import seal_loser_display_name_aliases, seal_summary
    from app.services.platform_audit import record_platform_audit_sync

    preview = preview_change_keeper(
        db,
        current_keeper_id=current_keeper_id,
        new_keeper_id=new_keeper_id,
        audit_note=audit_note,
        allow_open_channel_keeper=allow_open_channel_keeper,
    )
    cur = db.get(DimCustomer, int(current_keeper_id))
    new = db.get(DimCustomer, int(new_keeper_id))
    assert cur is not None and new is not None
    actor = (performed_by or "steward").strip() or "steward"
    stamp = datetime.now(timezone.utc).isoformat()
    note = preview["audit_note"]
    try:
        # Clear the new keeper's own redirect first, or the repoint would point it at itself.
        new.merged_into_customer_id = None
        new.customer_status = _status_after(cur)
        db.add(new)
        db.flush()
        expected = count_customer_fk_refs(db, int(cur.id))
        stats = repoint_customer_footprint_full(
            db, loser_id=int(cur.id), keeper_id=int(new.id), expected_counts=expected
        )
        cur.merged_into_customer_id = int(new.id)
        cur.customer_status = "merged"
        db.add(cur)
        line = (
            f"[customer keeper change {stamp}] keeper={new.id}; was={cur.id}; by={actor}; note={note[:300]}"
        )
        new.notes_summary = f"{(new.notes_summary or '').strip()}\n{line}".strip()[:512]
        db.flush()
        seal = seal_loser_display_name_aliases(db, keeper_id=int(new.id), loser_ids=[int(cur.id)], audit_note=note)
        record_platform_audit_sync(
            db,
            None,
            area="admin",
            action="customer_change_keeper",
            target_type="customer",
            target_id=str(new.id),
            detail={
                "new_keeper_id": int(new.id),
                "previous_keeper_id": int(cur.id),
                "rows_moved": preview["rows_to_move"],
                "other_merged_records_redirected": preview["other_merged_records_redirected"],
                "alias_seal": seal_summary(seal),
                "audit_note": note[:400],
            },
            actor_label=actor,
        )
        db.commit()
    except (CustomerFullRepointAbortError, IntegrityError) as exc:
        db.rollback()
        raise CustomerKeeperChangeError(f"Keeper change rolled back: {exc}") from exc

    logger.info(
        "customer_change_keeper new=%s previous=%s rows=%s alias_seal=%s",
        new.id,
        cur.id,
        preview["rows_to_move"],
        seal_summary(seal),
    )
    return {
        "dry_run": False,
        "new_keeper_id": int(new.id),
        "previous_keeper_id": int(cur.id),
        "rows_moved": preview["rows_to_move"],
        "repoint_stats": stats,
        "other_merged_records_redirected": preview["other_merged_records_redirected"],
        **seal,
    }
