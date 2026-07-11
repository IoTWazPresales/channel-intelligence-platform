"""Mint approved customer aliases when masters are full-merged (seal future DSI resolution)."""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.dimensions import DimCustomer
from app.services.commercial_planner.open_channel_customer import OPEN_CHANNEL_CUSTOMER_CODE
from app.services.customer_merge_redirect import follow_customer_merge_redirect
from app.services.imports.dsi_customer_alias_scope import (
    insert_approved_customer_alias_on_conflict_do_nothing,
    lookup_approved_customer_alias_for_scope,
)
from app.services.imports.provisional_entity_identity import customer_source_token_alias_key


def _is_open_channel_customer(row: DimCustomer | None) -> bool:
    if row is None:
        return False
    return str(row.code or "").strip().upper() == OPEN_CHANNEL_CUSTOMER_CODE


def seal_loser_display_name_aliases(
    db: Session,
    *,
    keeper_id: int,
    loser_ids: list[int],
    audit_note: str,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Mint global approved aliases: each loser's display name → keeper.

    Conflict with a third customer's alias is reported (never overwritten, never abort).
    Idempotent when the alias already points at the keeper.
    If a global alias still points at the loser tombstone, reassign it to the keeper
    (same intent as merge alias repoint).
    """
    kid = int(keeper_id)
    minted: list[dict[str, Any]] = []
    reassigned: list[dict[str, Any]] = []
    conflicts: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    note_tail = (audit_note or "").strip()[:200]

    for lid in loser_ids:
        loser = db.get(DimCustomer, int(lid))
        if loser is None:
            continue
        raw = (loser.name or "").strip()
        nt = customer_source_token_alias_key(raw)
        if not nt:
            skipped.append({"loser_id": int(lid), "reason": "empty_alias_key"})
            continue

        existing = lookup_approved_customer_alias_for_scope(
            db,
            normalized_token=nt,
            source_definition_id=None,
            distributor_id=None,
        )
        if existing is not None:
            existing_cid = int(existing.customer_id)
            if existing_cid == kid:
                skipped.append(
                    {
                        "loser_id": int(lid),
                        "normalized_token": nt,
                        "reason": "already_sealed",
                        "alias_id": int(existing.id),
                    }
                )
            elif existing_cid == int(lid):
                entry = {
                    "loser_id": int(lid),
                    "normalized_token": nt,
                    "alias_id": int(existing.id),
                    "from_customer_id": existing_cid,
                    "to_customer_id": kid,
                }
                if not dry_run:
                    existing.customer_id = kid
                    existing.notes = (
                        f"{(existing.notes or '').strip()}\n"
                        f"[alias seal reassign] loser_id={int(lid)}; {note_tail}"
                    ).strip()[:2000]
                    db.add(existing)
                reassigned.append(entry)
            else:
                conflicts.append(
                    {
                        "loser_id": int(lid),
                        "loser_name": raw[:120],
                        "normalized_token": nt,
                        "existing_customer_id": existing_cid,
                        "target_customer_id": kid,
                        "alias_id": int(existing.id),
                    }
                )
            continue

        if dry_run:
            minted.append(
                {
                    "loser_id": int(lid),
                    "alias_id": None,
                    "normalized_token": nt,
                    "raw_token": raw[:512],
                    "dry_run": True,
                }
            )
            continue

        new_id = insert_approved_customer_alias_on_conflict_do_nothing(
            db,
            customer_id=kid,
            raw_token=raw[:512],
            normalized_token=nt,
            source_definition_id=None,
            distributor_id=None,
            dealer_group_token=None,
            notes=f"[customer-full merge alias seal] loser_id={int(lid)}; {note_tail}",
            created_from_import_job_id=None,
            import_entity_mapping_candidate_id=None,
        )
        if new_id is not None:
            minted.append(
                {
                    "loser_id": int(lid),
                    "alias_id": int(new_id),
                    "normalized_token": nt,
                    "raw_token": raw[:512],
                }
            )
            continue

        again = lookup_approved_customer_alias_for_scope(
            db,
            normalized_token=nt,
            source_definition_id=None,
            distributor_id=None,
        )
        if again is not None and int(again.customer_id) == kid:
            skipped.append(
                {
                    "loser_id": int(lid),
                    "normalized_token": nt,
                    "reason": "already_sealed_race",
                    "alias_id": int(again.id),
                }
            )
        elif again is not None and int(again.customer_id) == int(lid):
            again.customer_id = kid
            db.add(again)
            reassigned.append(
                {
                    "loser_id": int(lid),
                    "normalized_token": nt,
                    "alias_id": int(again.id),
                    "from_customer_id": int(lid),
                    "to_customer_id": kid,
                    "reason": "race_reassign",
                }
            )
        elif again is not None:
            conflicts.append(
                {
                    "loser_id": int(lid),
                    "loser_name": raw[:120],
                    "normalized_token": nt,
                    "existing_customer_id": int(again.customer_id),
                    "target_customer_id": kid,
                    "alias_id": int(again.id),
                }
            )
        else:
            conflicts.append(
                {
                    "loser_id": int(lid),
                    "loser_name": raw[:120],
                    "normalized_token": nt,
                    "existing_customer_id": None,
                    "target_customer_id": kid,
                    "reason": "insert_blocked_unknown",
                }
            )

    return {
        "alias_seal_minted": minted,
        "alias_seal_reassigned": reassigned,
        "alias_seal_conflicts": conflicts,
        "alias_seal_skipped": skipped,
    }


def backfill_merged_customer_alias_seals(
    db: Session,
    *,
    dry_run: bool = True,
    audit_note: str = "backfill merged customer alias seal",
    limit: int | None = None,
) -> dict[str, Any]:
    """Seal display-name aliases for every soft-redirected customer → terminal survivor.

    Default is dry_run=True (no writes). Never overwrites a third-party alias.
    """
    rows = db.execute(
        select(DimCustomer.id, DimCustomer.name, DimCustomer.code, DimCustomer.merged_into_customer_id)
        .where(DimCustomer.merged_into_customer_id.is_not(None))
        .order_by(DimCustomer.id.asc())
    ).all()
    if limit is not None:
        rows = rows[: max(0, int(limit))]

    by_survivor: dict[int, list[int]] = {}
    skipped_cycles: list[dict[str, Any]] = []
    for r in rows:
        lid = int(r.id)
        loser = db.get(DimCustomer, lid)
        if _is_open_channel_customer(loser):
            skipped_cycles.append(
                {
                    "loser_id": lid,
                    "reason": "open_channel_excluded",
                    "code": getattr(loser, "code", None),
                }
            )
            continue
        terminal, followed = follow_customer_merge_redirect(db, lid)
        if not followed or terminal == lid:
            skipped_cycles.append({"loser_id": lid, "reason": "no_terminal_redirect"})
            continue
        terminal_row = db.get(DimCustomer, int(terminal))
        if _is_open_channel_customer(terminal_row):
            skipped_cycles.append(
                {
                    "loser_id": lid,
                    "reason": "open_channel_survivor_excluded",
                    "terminal_id": int(terminal),
                }
            )
            continue
        by_survivor.setdefault(int(terminal), []).append(lid)

    minted: list[dict[str, Any]] = []
    reassigned: list[dict[str, Any]] = []
    conflicts: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = list(skipped_cycles)
    survivors_touched = 0

    for kid, loser_ids in sorted(by_survivor.items(), key=lambda kv: kv[0]):
        survivors_touched += 1
        out = seal_loser_display_name_aliases(
            db,
            keeper_id=kid,
            loser_ids=loser_ids,
            audit_note=audit_note,
            dry_run=dry_run,
        )
        minted.extend(out["alias_seal_minted"])
        reassigned.extend(out.get("alias_seal_reassigned") or [])
        conflicts.extend(out["alias_seal_conflicts"])
        skipped.extend(out["alias_seal_skipped"])

    if not dry_run:
        db.commit()

    return {
        "dry_run": dry_run,
        "merged_customers_scanned": len(rows),
        "survivors_touched": survivors_touched,
        "would_mint_or_minted": len(minted),
        "would_reassign_or_reassigned": len(reassigned),
        "conflicts": len(conflicts),
        "skipped": len(skipped),
        "alias_seal_minted": minted,
        "alias_seal_reassigned": reassigned,
        "alias_seal_conflicts": conflicts,
        "alias_seal_skipped": skipped,
    }
