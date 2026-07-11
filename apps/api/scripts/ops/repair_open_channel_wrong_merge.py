"""Repair: restore system OPEN_CHANNEL as canonical after wrong-direction merge into TMP.

History on cip (observed 2026-07-11):
  OPEN_CHANNEL id=1 was soft-redirected into TMP-CUST-… id=19 (survivor=19, loser=1).
  OPEN_CHANNEL is system reference data and must remain the live account.

This script:
  1) verifies the known-bad shape
  2) restores id=1 as active (clears merged_into)
  3) full-repoints id=19 → id=1 (FKs + aliases)
  4) soft-redirects the TMP into OPEN_CHANNEL

Safety:
  - dry-run by default
  - requires --apply --i-understand
  - refuses unless current_database() == 'cip' (or --allow-non-cip)
  - refuses unless OPEN_CHANNEL id/code and TMP id/code match expected shape

Usage (from apps/api):
  python scripts/ops/repair_open_channel_wrong_merge.py
  python scripts/ops/repair_open_channel_wrong_merge.py --apply --i-understand
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import text

_API_ROOT = Path(__file__).resolve().parents[2]
if str(_API_ROOT) not in sys.path:
    sys.path.insert(0, str(_API_ROOT))

from app.db.session_sync import SessionLocal  # noqa: E402
from app.models.dimensions import DimCustomer  # noqa: E402
from app.services.commercial_planner.open_channel_customer import (  # noqa: E402
    OPEN_CHANNEL_CUSTOMER_CODE,
    OPEN_CHANNEL_CUSTOMER_NAME,
)
from app.services.customer_full_repoint import (  # noqa: E402
    CustomerFullRepointAbortError,
    count_customer_fk_refs,
    repoint_customer_footprint_full,
)
from app.services.customer_merge_alias_seal import seal_loser_display_name_aliases  # noqa: E402

# Known bad pair on cip (TMP absorbed system OPEN_CHANNEL).
_EXPECTED_OPEN_CHANNEL_ID = 1
_EXPECTED_TMP_ID = 19
_EXPECTED_TMP_CODE_PREFIX = "TMP-CUST-"


def _current_database(session) -> str:
    return str(session.execute(text("SELECT current_database()")).scalar() or "")


def _audit_snapshot(row: DimCustomer) -> dict:
    return {
        "id": int(row.id),
        "code": row.code,
        "name": row.name,
        "customer_status": row.customer_status,
        "merged_into_customer_id": row.merged_into_customer_id,
    }


def verify_and_plan(session) -> dict:
    oc = session.get(DimCustomer, _EXPECTED_OPEN_CHANNEL_ID)
    tmp = session.get(DimCustomer, _EXPECTED_TMP_ID)
    if oc is None or tmp is None:
        raise SystemExit("Expected OPEN_CHANNEL id=1 and TMP id=19 rows missing")
    if str(oc.code or "") != OPEN_CHANNEL_CUSTOMER_CODE:
        raise SystemExit(f"id=1 code is {oc.code!r}, expected {OPEN_CHANNEL_CUSTOMER_CODE!r}")
    if not str(tmp.code or "").startswith(_EXPECTED_TMP_CODE_PREFIX):
        raise SystemExit(f"id=19 code {tmp.code!r} is not a TMP-CUST provisional")
    if str(tmp.name or "").strip().lower() != OPEN_CHANNEL_CUSTOMER_NAME.lower():
        raise SystemExit(f"id=19 name {tmp.name!r} is not Open Channel")
    if oc.merged_into_customer_id != _EXPECTED_TMP_ID:
        raise SystemExit(
            f"OPEN_CHANNEL.merged_into_customer_id={oc.merged_into_customer_id!r}; "
            f"expected {_EXPECTED_TMP_ID} (wrong-merge shape not present — abort)"
        )
    if tmp.merged_into_customer_id is not None:
        raise SystemExit(f"TMP id=19 already redirected to {tmp.merged_into_customer_id}")

    tmp_refs = count_customer_fk_refs(session, _EXPECTED_TMP_ID)
    oc_refs = count_customer_fk_refs(session, _EXPECTED_OPEN_CHANNEL_ID)
    return {
        "open_channel": _audit_snapshot(oc),
        "tmp": _audit_snapshot(tmp),
        "tmp_fk_refs_total": sum(tmp_refs.values()),
        "tmp_fk_refs": tmp_refs,
        "open_channel_fk_refs_total": sum(oc_refs.values()),
        "open_channel_fk_refs": oc_refs,
        "plan": [
            "clear OPEN_CHANNEL.merged_into + set status active",
            "repoint TMP-19 footprint → OPEN_CHANNEL id=1",
            "soft-redirect TMP-19 → OPEN_CHANNEL",
            "seal TMP display-name alias onto OPEN_CHANNEL",
        ],
    }


def apply_repair(session) -> dict:
    plan = verify_and_plan(session)
    oc = session.get(DimCustomer, _EXPECTED_OPEN_CHANNEL_ID)
    tmp = session.get(DimCustomer, _EXPECTED_TMP_ID)
    assert oc is not None and tmp is not None

    stamp = datetime.now(timezone.utc).isoformat()
    # 1) Restore system row as live keeper before repoint.
    oc.merged_into_customer_id = None
    if (oc.customer_status or "").strip().lower() in ("merged", "inactive"):
        oc.customer_status = "active"
    oc.notes_summary = (
        f"{(oc.notes_summary or '').strip()}\n"
        f"[open-channel repair {stamp}] restored canonical OPEN_CHANNEL; "
        f"repointing TMP id={_EXPECTED_TMP_ID} into this row"
    ).strip()[:512]
    session.add(oc)
    session.flush()

    # 2) Count after clearing OC redirect so expected_counts match live state.
    expected = count_customer_fk_refs(session, _EXPECTED_TMP_ID)
    # Label keys used by repoint expected_counts are "table.column".
    expected_counts = {k: int(v) for k, v in expected.items()}

    try:
        repoint_stats = repoint_customer_footprint_full(
            session,
            loser_id=_EXPECTED_TMP_ID,
            keeper_id=_EXPECTED_OPEN_CHANNEL_ID,
            expected_counts=expected_counts,
        )
    except CustomerFullRepointAbortError as exc:
        session.rollback()
        raise SystemExit(f"Repoint aborted: {exc}") from exc

    # 3) Soft-redirect TMP → OPEN_CHANNEL.
    tmp.merged_into_customer_id = _EXPECTED_OPEN_CHANNEL_ID
    tmp.customer_status = "merged"
    tmp.notes_summary = (
        f"{(tmp.notes_summary or '').strip()}\n"
        f"[open-channel repair {stamp}] provisional Open Channel redirected into "
        f"system OPEN_CHANNEL id={_EXPECTED_OPEN_CHANNEL_ID} (reverse of wrong merge)"
    ).strip()[:512]
    session.add(tmp)
    session.flush()

    # 4) Seal display-name alias (idempotent / conflict-safe).
    seal = seal_loser_display_name_aliases(
        session,
        keeper_id=_EXPECTED_OPEN_CHANNEL_ID,
        loser_ids=[_EXPECTED_TMP_ID],
        audit_note="open-channel repair seal",
        dry_run=False,
    )

    session.commit()

    oc2 = session.get(DimCustomer, _EXPECTED_OPEN_CHANNEL_ID)
    tmp2 = session.get(DimCustomer, _EXPECTED_TMP_ID)
    assert oc2 is not None and tmp2 is not None
    return {
        "plan_before": plan,
        "repoint_stats": repoint_stats,
        "alias_seal": seal,
        "open_channel_after": _audit_snapshot(oc2),
        "tmp_after": _audit_snapshot(tmp2),
        "open_channel_fk_refs_after": count_customer_fk_refs(session, _EXPECTED_OPEN_CHANNEL_ID),
        "tmp_fk_refs_after": count_customer_fk_refs(session, _EXPECTED_TMP_ID),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--i-understand", action="store_true")
    parser.add_argument("--allow-non-cip", action="store_true")
    parser.add_argument("--json-out", type=str, default=None)
    args = parser.parse_args()

    if args.apply and not args.i_understand:
        print("Refusing --apply without --i-understand", file=sys.stderr)
        return 2

    with SessionLocal() as session:
        db_name = _current_database(session)
        if db_name != "cip" and not args.allow_non_cip:
            print(f"Refusing: current_database()={db_name!r}", file=sys.stderr)
            return 2
        print(f"database={db_name} dry_run={not args.apply}")

        if not args.apply:
            report = verify_and_plan(session)
            print(json.dumps(report, indent=2, default=str))
            print(
                "\nDry-run only. To apply:\n"
                "  python scripts/ops/repair_open_channel_wrong_merge.py "
                "--apply --i-understand"
            )
        else:
            report = apply_repair(session)
            print(json.dumps(report, indent=2, default=str))

    if args.json_out:
        Path(args.json_out).write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
        print(f"wrote {args.json_out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
