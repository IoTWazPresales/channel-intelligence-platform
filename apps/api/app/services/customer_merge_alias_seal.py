"""Alias seal for customer merges (BACKLOG-081).

A confirmed merge mints an approved, global customer alias from each merged-away record's name to
the keeper, so a later file that still carries the old name resolves to the keeper and does not
come back as steward work.

Rules:
- one alias per distinct lookup key of the name. Resolvers look aliases up by two keys: the
  punctuation-free SSOT key (``customer_source_token_alias_key``) and the plain lowercased key
  (``_norm_key``). When they differ, both are sealed.
- an alias that already points at the keeper is left alone (idempotent);
- an alias that points at the merged-away record, or at another record already merged into the
  keeper, is moved to the keeper;
- an alias that points at a third customer is reported as a conflict, never overwritten, and the
  merge still goes ahead;
- OPEN_CHANNEL is never sealed in either direction.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.dimensions import DimCustomer
from app.services.commercial_planner.open_channel_customer import OPEN_CHANNEL_CUSTOMER_CODE
from app.services.customer_test_fixtures import is_test_fixture_customer
from app.services.imports.distributor_sales_inventory import _norm_key
from app.services.imports.dsi_customer_alias_scope import (
    insert_approved_customer_alias_on_conflict_do_nothing,
    lookup_approved_customer_alias_for_scope,
)
from app.services.imports.provisional_entity_identity import customer_source_token_alias_key
from app.services.merge_redirect import follow_customer_merge_redirect_sync, load_customer_redirect_map

SEAL_NOTE_PREFIX = "[customer merge alias seal]"


def loser_alias_keys(name: str | None) -> list[str]:
    """Distinct alias lookup keys for a merged-away name (SSOT key first)."""
    keys: list[str] = []
    for key in (customer_source_token_alias_key(name), _norm_key(name)[:512]):
        if key and key not in keys:
            keys.append(key)
    return keys


def _is_open_channel(row: DimCustomer | None) -> bool:
    return row is not None and str(row.code or "").strip().upper() == OPEN_CHANNEL_CUSTOMER_CODE


def seal_loser_display_name_aliases(
    db: Session,
    *,
    keeper_id: int,
    loser_ids: list[int],
    audit_note: str,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Mint or move global approved aliases from each loser's name to the keeper. Does not commit."""
    kid = int(keeper_id)
    minted: list[dict[str, Any]] = []
    reassigned: list[dict[str, Any]] = []
    conflicts: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    note_tail = (audit_note or "").strip()[:200]

    keeper = db.get(DimCustomer, kid)
    for raw_lid in loser_ids:
        lid = int(raw_lid)
        loser = db.get(DimCustomer, lid)
        if loser is None:
            skipped.append({"loser_id": lid, "reason": "loser_missing"})
            continue
        if _is_open_channel(loser) or _is_open_channel(keeper):
            skipped.append({"loser_id": lid, "reason": "open_channel_excluded"})
            continue
        raw = (loser.name or "").strip()
        keys = loser_alias_keys(raw)
        if not keys:
            skipped.append({"loser_id": lid, "reason": "empty_alias_key"})
            continue

        for nt in keys:
            existing = lookup_approved_customer_alias_for_scope(
                db, normalized_token=nt, source_definition_id=None, distributor_id=None
            )
            if existing is not None:
                owner = int(existing.customer_id)
                if owner == kid:
                    skipped.append(
                        {"loser_id": lid, "normalized_token": nt, "reason": "already_sealed", "alias_id": int(existing.id)}
                    )
                elif owner == lid or follow_customer_merge_redirect_sync(db, owner) == kid:
                    reassigned.append(
                        {
                            "loser_id": lid,
                            "normalized_token": nt,
                            "alias_id": int(existing.id),
                            "from_customer_id": owner,
                            "to_customer_id": kid,
                        }
                    )
                    if not dry_run:
                        existing.customer_id = kid
                        existing.notes = (
                            f"{(existing.notes or '').strip()}\n{SEAL_NOTE_PREFIX} moved from {owner}; "
                            f"loser_id={lid}; {note_tail}"
                        ).strip()[:2000]
                        db.add(existing)
                else:
                    conflicts.append(
                        {
                            "loser_id": lid,
                            "loser_name": raw[:120],
                            "normalized_token": nt,
                            "existing_customer_id": owner,
                            "target_customer_id": kid,
                            "alias_id": int(existing.id),
                        }
                    )
                continue

            if dry_run:
                minted.append({"loser_id": lid, "alias_id": None, "normalized_token": nt, "raw_token": raw[:512]})
                continue
            new_id = insert_approved_customer_alias_on_conflict_do_nothing(
                db,
                customer_id=kid,
                raw_token=raw[:512],
                normalized_token=nt,
                source_definition_id=None,
                distributor_id=None,
                dealer_group_token=None,
                notes=f"{SEAL_NOTE_PREFIX} loser_id={lid}; {note_tail}",
                created_from_import_job_id=None,
                import_entity_mapping_candidate_id=None,
            )
            if new_id is None:
                # Lost a race with another writer: report, never overwrite.
                conflicts.append(
                    {
                        "loser_id": lid,
                        "loser_name": raw[:120],
                        "normalized_token": nt,
                        "existing_customer_id": None,
                        "target_customer_id": kid,
                        "reason": "insert_blocked",
                    }
                )
                continue
            minted.append({"loser_id": lid, "alias_id": int(new_id), "normalized_token": nt, "raw_token": raw[:512]})

    db.flush()
    return {
        "alias_seal_minted": minted,
        "alias_seal_reassigned": reassigned,
        "alias_seal_conflicts": conflicts,
        "alias_seal_skipped": skipped,
    }


def seal_summary(result: dict[str, Any]) -> dict[str, int]:
    return {
        "minted": len(result.get("alias_seal_minted") or []),
        "reassigned": len(result.get("alias_seal_reassigned") or []),
        "conflicts": len(result.get("alias_seal_conflicts") or []),
        "skipped": len(result.get("alias_seal_skipped") or []),
    }


def backfill_merged_customer_alias_seals(
    db: Session,
    *,
    dry_run: bool = True,
    audit_note: str = "backfill merged customer alias seal",
) -> dict[str, Any]:
    """Seal every past merge to its final keeper. Test fixtures and OPEN_CHANNEL are left untouched.

    Default is a dry run. Commits only when ``dry_run`` is False.
    """
    rows = db.execute(
        select(DimCustomer.id, DimCustomer.code, DimCustomer.name, DimCustomer.merged_into_customer_id)
        .where(DimCustomer.merged_into_customer_id.is_not(None))
        .order_by(DimCustomer.id.asc())
    ).all()
    redirect = load_customer_redirect_map(db)
    codes = {int(r[0]): (str(r[1] or ""), str(r[2] or "")) for r in db.execute(select(DimCustomer.id, DimCustomer.code, DimCustomer.name))}

    by_keeper: dict[int, list[int]] = {}
    fixture_skipped = 0
    excluded: list[dict[str, Any]] = []
    for r in rows:
        lid = int(r.id)
        kid = int(redirect.get(lid, lid))
        if kid == lid:
            excluded.append({"loser_id": lid, "reason": "merge_cycle"})
            continue
        if is_test_fixture_customer(*codes.get(lid, ("", ""))) or is_test_fixture_customer(*codes.get(kid, ("", ""))):
            fixture_skipped += 1
            continue
        if OPEN_CHANNEL_CUSTOMER_CODE in (codes.get(lid, ("", ""))[0].upper(), codes.get(kid, ("", ""))[0].upper()):
            excluded.append({"loser_id": lid, "reason": "open_channel_excluded"})
            continue
        by_keeper.setdefault(kid, []).append(lid)

    minted: list[dict[str, Any]] = []
    reassigned: list[dict[str, Any]] = []
    conflicts: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = list(excluded)
    for kid, loser_ids in sorted(by_keeper.items()):
        out = seal_loser_display_name_aliases(
            db, keeper_id=kid, loser_ids=loser_ids, audit_note=audit_note, dry_run=dry_run
        )
        minted.extend(out["alias_seal_minted"])
        reassigned.extend(out["alias_seal_reassigned"])
        conflicts.extend(out["alias_seal_conflicts"])
        skipped.extend(out["alias_seal_skipped"])

    if dry_run:
        db.rollback()
    else:
        db.commit()
    return {
        "dry_run": dry_run,
        "merged_records": len(rows) - fixture_skipped,
        "test_fixture_merges_left_untouched": fixture_skipped,
        "keepers": len(by_keeper),
        "minted": len(minted),
        "reassigned": len(reassigned),
        "conflicts": len(conflicts),
        "skipped": len(skipped),
        "alias_seal_minted": minted,
        "alias_seal_reassigned": reassigned,
        "alias_seal_conflicts": conflicts,
        "alias_seal_skipped": skipped,
    }
