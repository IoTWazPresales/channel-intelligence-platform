"""List GET routes (no DB access) to pick heavy product-keyed read paths."""
import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3] / "apps" / "api"))

from app.main import app  # noqa: E402

pat = re.compile(sys.argv[1] if len(sys.argv) > 1 else ".")
for r in app.routes:
    methods = getattr(r, "methods", None) or set()
    if "GET" in methods and pat.search(r.path):
        print(r.path, getattr(r.endpoint, "__module__", ""), r.endpoint.__name__)
