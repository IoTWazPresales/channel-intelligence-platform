"""GOV-008 N-0065 VER2 mutation: an empty scope is written as '' instead of the '!' sentinel.

Under 0025 '' is open, so this reintroduces a fail-open for a non-admin with no assignment.
Run from the project root with the API virtualenv. The file is restored in a finally block and its
sha256 is compared before/after. Tests run on cip_test through N0065_ver2_run_cip_test.py.
"""

from __future__ import annotations

import hashlib
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
TARGET = os.path.join(ROOT, "apps", "api", "app", "core", "product_line_scope.py")
OLD = 'return ",".join(sorted(lines)) or NO_PRODUCT_LINES'
NEW = 'return ",".join(sorted(lines)) or ""'
FILES = ",".join([
    "tests/test_product_line_scope_n0065.py",
    "tests/test_product_line_session_listener_n0065.py",
])


def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


orig = open(TARGET, "rb").read()
print("before sha256 =", sha(orig)[:16])
assert orig.count(OLD.encode()) == 1
try:
    open(TARGET, "wb").write(orig.replace(OLD.encode(), NEW.encode()))
    print("mutated: scope_csv(empty) -> ''")
    env = dict(os.environ, N0065_VER2_ONLY=FILES)
    out = subprocess.run([sys.executable, os.path.join(HERE, "N0065_ver2_run_cip_test.py"), "-q", "-x", "--no-header",
                          "-o", "addopts="] if False else
                         [sys.executable, os.path.join(HERE, "N0065_ver2_run_cip_test.py"), "-rf", "--tb=line"],
                         cwd=ROOT, env=env, capture_output=True, text=True, timeout=900)
    lines = (out.stdout or "").splitlines()
    for ln in lines[-40:]:
        if True:
            print("  ", ln[:220])
    print("exit =", out.returncode)
finally:
    open(TARGET, "wb").write(orig)
    after = open(TARGET, "rb").read()
    print("after sha256 =", sha(after)[:16], "restored =", after == orig)
