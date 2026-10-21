"""GOV-008 N-0065 VER2: re-run the round-3 cip_test file set (same list as N0065_r3_final_run.py).

Run from the project root with the API virtualenv. Delegates to N0065_run_db_tests.py, which swaps
DATABASE_URL(_SYNC) to cip_test in-process, asserts the name and prints current_database().
The parity JSON goes to N0065_ver2_parity.json (the implementer's file is not overwritten).
Extra pytest args may be passed after the script name.
"""

from __future__ import annotations

import os
import runpy
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
API = os.path.join(ROOT, "apps", "api")
os.chdir(API)
sys.path.insert(0, API)

lists = runpy.run_path(os.path.join(HERE, "N0065_r3_final_run.py"), run_name="lists_only")
files = []
only = os.environ.get("N0065_VER2_ONLY")
if only:
    files = only.split(",")
else:
    for k in ("N0065", "ROUND1", "AUTH", "FIX4", "SAMPLE"):
        files += lists[k]
files = ["tests/test_product_line_rls_n0065_db.py"] * 0 + files
present = [p for p in files if os.path.exists(p)]
print("test files (plus the DB module added by the runner):", len(present), "missing:", [p for p in files if p not in present])
os.environ["N0065_PARITY_OUT"] = os.path.join(HERE, "N0065_ver2_parity.json")
sys.argv = ["N0065_run_db_tests.py", *present, "-p", "no:cacheprovider", *sys.argv[1:]]
runpy.run_path(os.path.join(HERE, "N0065_run_db_tests.py"), run_name="__main__")
