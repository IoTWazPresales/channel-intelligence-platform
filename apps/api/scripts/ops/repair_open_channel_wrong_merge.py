"""Repair a customer merge that went the wrong way round OPEN_CHANNEL.

OPEN_CHANNEL is system reference data and must stay the live record. If a merge ever pointed the
OPEN_CHANNEL row at another customer (the July 2026 incident: id 1 merged into a TMP-CUST "Open
Channel"), this restores OPEN_CHANNEL as the keeper: every row moves back to it, the other record
becomes merged into OPEN_CHANNEL. It uses the same keeper-change path the steward panel uses.

It also lists records merged INTO OPEN_CHANNEL so a wrong absorb can be seen; it never undoes those.

Usage (from apps/api):
  python scripts/ops/repair_open_channel_wrong_merge.py                     # dry run
  python scripts/ops/repair_open_channel_wrong_merge.py --apply --expect-db cip_n0095
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from sqlalchemy import select, text

_API_ROOT = Path(__file__).resolve().parents[2]
if str(_API_ROOT) not in sys.path:
    sys.path.insert(0, str(_API_ROOT))

from app.db.session_sync import SessionLocal  # noqa: E402
from app.models.dimensions import DimCustomer  # noqa: E402
from app.services.commercial_planner.open_channel_customer import OPEN_CHANNEL_CUSTOMER_CODE  # noqa: E402
from app.services.customer_merge_keeper import confirm_change_keeper, preview_change_keeper  # noqa: E402

NOTE = "repair: OPEN_CHANNEL restored as keeper"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--expect-db", default=None, help="required with --apply; must equal current_database()")
    args = parser.parse_args(argv)

    with SessionLocal() as db:
        current = str(db.execute(text("SELECT current_database()")).scalar() or "")
        print(f"current_database()={current}")
        oc = db.scalar(select(DimCustomer).where(DimCustomer.code == OPEN_CHANNEL_CUSTOMER_CODE))
        if oc is None:
            print("refused: no OPEN_CHANNEL customer")
            return 2
        absorbed = db.execute(
            select(DimCustomer.id, DimCustomer.code, DimCustomer.name).where(
                DimCustomer.merged_into_customer_id == int(oc.id)
            )
        ).all()
        print(f"OPEN_CHANNEL id={oc.id} merged_into={oc.merged_into_customer_id}")
        print(f"records merged into OPEN_CHANNEL: {len(absorbed)}")
        for r in absorbed:
            print(f"  {r.id} {r.code} {r.name!r}")
        if oc.merged_into_customer_id is None:
            print("OPEN_CHANNEL is the keeper; nothing to repair")
            return 0

        wrong_keeper = int(oc.merged_into_customer_id)
        plan = preview_change_keeper(
            db,
            current_keeper_id=wrong_keeper,
            new_keeper_id=int(oc.id),
            audit_note=NOTE,
            allow_open_channel_keeper=True,
        )
        print(json.dumps({k: plan[k] for k in ("current_keeper", "new_keeper", "rows_to_move")}, indent=2, default=str))
        if not args.apply:
            print("dry run: nothing written")
            return 0
        if args.expect_db != current:
            print(f"refused: --apply needs --expect-db {current!r} (got {args.expect_db!r})")
            return 2
        out = confirm_change_keeper(
            db,
            current_keeper_id=wrong_keeper,
            new_keeper_id=int(oc.id),
            audit_note=NOTE,
            performed_by="repair_open_channel_wrong_merge",
            allow_open_channel_keeper=True,
        )
        print(json.dumps({k: out[k] for k in ("new_keeper_id", "previous_keeper_id", "rows_moved")}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
