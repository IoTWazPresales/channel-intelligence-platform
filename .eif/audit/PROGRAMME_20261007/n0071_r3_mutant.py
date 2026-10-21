"""N-0071 round 3 mutation checks: mutate one file, run the strict-pair tests, restore byte for byte.

Run from the repo root with the api venv python: python n0071_r3_mutant.py <mutant>
Mutants:
  pro_rata_full      helper value of a partly shipped line = full stored amount (ORM and SQL text)
  pro_rata_full_orm  the same, ORM form only
  channel_ops        the three channel ops readers total the stored quantity again
  net_requirement    in-transit totals the stored quantity again
  po_auto_link       proposals use the stored quantity again
  po_reconciliation  pipeline totals the stored quantity again
  hint_1h            1H hint totals the stored quantity again
  grid_still_to_ship still_to_ship = stored quantity
"""
from __future__ import annotations

import hashlib
import subprocess
import sys
from pathlib import Path

API = Path("apps/api")
HELPER = "app/services/shipment_strict_pair.py"
ORM_PRO_RATA = "(counted_qty > 0, model.amount * counted_qty / func.nullif(model.quantity, 0)),"
SQL_PRO_RATA = (
    '    "WHEN twin_rem.counted_qty > 0 THEN fact_inbound_shipment.amount * twin_rem.counted_qty "\n'
    '    "/ nullif(fact_inbound_shipment.quantity, 0) "\n'
)
MUTANTS: dict[str, tuple[str, list[tuple[str, str, int]]]] = {
    "pro_rata_full": (
        HELPER,
        [
            (ORM_PRO_RATA, "(counted_qty > 0, model.amount),", 1),
            (SQL_PRO_RATA, '    "WHEN twin_rem.counted_qty > 0 THEN fact_inbound_shipment.amount "\n', 1),
        ],
    ),
    "pro_rata_full_orm": (HELPER, [(ORM_PRO_RATA, "(counted_qty > 0, model.amount),", 1)]),
    "channel_ops": (
        "app/api/v1/endpoints/channel_ops.py",
        [("func.sum(twin.counted_quantity)", "func.sum(FactInboundShipment.quantity)", 3)],
    ),
    "net_requirement": (
        "app/services/lineup/net_requirement.py",
        [("func.sum(twin.counted_quantity)", "func.sum(FactInboundShipment.quantity)", 1)],
    ),
    "po_auto_link": (
        "app/services/commercial_planner/lineup_po_auto_link.py",
        [("ship_qty = counted_qty_by_fact[int(ship.id)]", "ship_qty = float(ship.quantity or 0)", 1)],
    ),
    "po_reconciliation": (
        "app/services/commercial_planner/lineup_po_reconciliation.py",
        [("func.sum(twin.counted_quantity)", "func.sum(EV.quantity)", 1)],
    ),
    "hint_1h": (
        "app/services/commercial_planner/lineup_bulk_rederivation.py",
        [("func.sum(twin.counted_quantity)", "func.sum(FactInboundShipment.quantity)", 1)],
    ),
    "grid_still_to_ship": (
        "app/api/v1/endpoints/shipping.py",
        [("select(FactInboundShipment.id, twin.counted_quantity)", "select(FactInboundShipment.id, FactInboundShipment.quantity)", 1)],
    ),
}

which = sys.argv[1]
if which == "net_requirement":
    # net_requirement.py is shared with another run (N-0065): mutate in memory, never write it.
    import os

    env = dict(os.environ, PYTHONPATH=str(Path(__file__).resolve().parent))
    target = API / MUTANTS[which][0]
    print(which, "(in-memory plugin)")
    print("sha256 before:", hashlib.sha256(target.read_bytes()).hexdigest())
    r = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "-p", "n0071_r3_mutant_plugin",
         "tests/test_shipment_strict_pair.py"],
        cwd=str(API), capture_output=True, text=True, env=env,
    )
    print("\n".join(ln for ln in r.stdout.splitlines() if ln.startswith("FAILED") or " passed" in ln or " failed" in ln))
    print("sha256 after:", hashlib.sha256(target.read_bytes()).hexdigest())
    raise SystemExit(0)
rel, edits = MUTANTS[which]
target = API / rel
original = target.read_bytes()
print(which, rel)
print("sha256 before:", hashlib.sha256(original).hexdigest())
crlf = b"\r\n" in original
src = original.decode("utf-8").replace("\r\n", "\n")
for old, new, n in edits:
    assert src.count(old) == n, (old, src.count(old))
    src = src.replace(old, new)
try:
    data = src.replace("\n", "\r\n") if crlf else src
    target.write_bytes(data.encode("utf-8"))
    r = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "tests/test_shipment_strict_pair.py"],
        cwd=str(API),
        capture_output=True,
        text=True,
    )
    lines = [ln for ln in r.stdout.splitlines() if ln.startswith("FAILED") or " passed" in ln or " failed" in ln]
    print("\n".join(lines))
finally:
    target.write_bytes(original)
print("sha256 after:", hashlib.sha256(target.read_bytes()).hexdigest())
