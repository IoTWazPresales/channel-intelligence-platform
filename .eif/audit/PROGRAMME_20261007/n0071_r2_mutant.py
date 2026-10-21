"""N-0071 round 2 mutation checks (remainder_zero | supply_no_rule): mutate, run the tests, restore.

Run from the repo root with the api venv python. Restores the helper byte-for-byte
(sha256 printed before and after). Mutant: remainder = 0 in the ORM form and the raw
SQL text, and every open twin is skipped (the D-0057 behaviour).
"""
from __future__ import annotations

import hashlib
import subprocess
import sys
from pathlib import Path

WHICH = sys.argv[1] if len(sys.argv) > 1 else "remainder_zero"
HELPER = Path(
    "apps/api/app/services/supply_overview.py" if WHICH == "supply_no_rule" else "apps/api/app/services/shipment_strict_pair.py"
)
original = HELPER.read_bytes()
print("sha256 before:", hashlib.sha256(original).hexdigest())
src = original.decode("utf-8").replace("\r\n", "\n")
edits = [
    (
        "remainder = case((w.c.open_qty > w.c.shipped_qty, w.c.open_qty - w.c.shipped_qty), else_=0)",
        "remainder = literal_column('0')",
    ),
    ("        w.c.open_qty <= w.c.shipped_qty,\n", "        w.c.open_qty == w.c.open_qty,\n"),
    (
        "    WHEN keyed.open_qty > keyed.shipped_qty THEN keyed.open_qty - keyed.shipped_qty\n",
        "    WHEN 1 = 0 THEN keyed.open_qty - keyed.shipped_qty\n",
    ),
]
if WHICH == "supply_no_rule":  # change A undone: the headline ignores the strict-pair rule
    edits = [("      AND {_KEPT}\n", "")]
for old, new in edits:
    assert src.count(old) == 1, old
    src = src.replace(old, new)
try:
    HELPER.write_text(src, encoding="utf-8")
    r = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "tests/test_shipment_strict_pair.py"],
        cwd="apps/api",
        capture_output=True,
        text=True,
    )
    lines = [ln for ln in r.stdout.splitlines() if ln.startswith("FAILED") or " passed" in ln or " failed" in ln]
    print("\n".join(lines))
finally:
    HELPER.write_bytes(original)
print("sha256 after:", hashlib.sha256(HELPER.read_bytes()).hexdigest())
