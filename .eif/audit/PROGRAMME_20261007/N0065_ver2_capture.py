"""GOV-008 N-0065 VER2: re-run the READ ONLY heavy-path capture (n0065_capture.py) for brief signals and
cover distribution under unset / '*' / NB, now that cip is at 0025.

Run from the project root with the API virtualenv:  python N0065_ver2_capture.py <tag>
Output JSON: N0065_ver2_cap_<tag>.json. n0065_capture.py opens every connection with
default_transaction_read_only=on and statement_timeout=60s (NullPool) and only issues GET requests.
"""

import os
import runpy
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
API = os.path.join(ROOT, "apps", "api")
os.chdir(API)
sys.path.insert(0, API)
tag = sys.argv[1] if len(sys.argv) > 1 else "a"
paths = ",".join("/" + p for p in ("api/v1/brief/signals", "api/v1/channel-ops/cover-distribution"))
sys.argv = ["n0065_capture.py", os.path.join(HERE, f"N0065_ver2_cap_{tag}.json"), "unset,star,NB", paths]
runpy.run_path(os.path.join(HERE, "n0065_capture.py"), run_name="__main__")
