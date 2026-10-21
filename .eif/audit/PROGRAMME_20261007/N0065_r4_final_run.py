"""N-0065 round 4 cip_test run: parity (0024/0025/0026) + lineage + N-0065 suites + round-2/3 set.

Run from apps/api with its virtualenv:  python <this> [all|parity|n0065] [extra pytest args]
Delegates to N0065_run_db_tests.py, which swaps DATABASE_URL(_SYNC) to cip_test in-process,
asserts the name, and prints current_database(). Parity JSON: N0065_r4_parity.json here.
"""

from __future__ import annotations

import os
import runpy
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
_r3 = runpy.run_path(os.path.join(HERE, "N0065_r3_final_run.py"))  # reuse the round-3 file lists

PARITY = ["tests/test_product_line_rls_parity_n0065_db.py"]
N0065 = [
    "tests/test_shipment_evidence_lineage_rls_n0065_db.py",
    "tests/test_product_line_session_listener_n0065.py",
    "tests/test_product_line_scope_n0065.py",
]


def main() -> None:
    which = sys.argv[1] if len(sys.argv) > 1 and not sys.argv[1].startswith("-") else "all"
    rest = sys.argv[2:] if which != "all" or (len(sys.argv) > 1 and not sys.argv[1].startswith("-")) else sys.argv[1:]
    os.environ["N0065_PARITY_OUT"] = os.path.join(HERE, "N0065_r4_parity.json")
    if which == "parity":
        files = PARITY
    elif which == "n0065":
        files = N0065
    else:
        files = PARITY + N0065 + [f for f in _r3["N0065"] if f not in PARITY + N0065] \
            + _r3["ROUND1"] + _r3["AUTH"] + _r3["FIX4"] + _r3["SAMPLE"]
    present = [p for p in files if os.path.exists(p)]
    missing = [p for p in files if not os.path.exists(p)]
    print("test files:", len(present) + 1, "missing:", missing)
    sys.argv = ["N0065_run_db_tests.py", *present, "-p", "no:cacheprovider", *rest]
    runpy.run_path(os.path.join(HERE, "N0065_run_db_tests.py"), run_name="__main__")


if __name__ == "__main__":
    main()
