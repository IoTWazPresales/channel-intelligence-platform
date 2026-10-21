"""GOV-008 N-0065 temporary source mutations (RUN-20261007-N0065-VER).

Usage (from the project root): python .eif/audit/PROGRAMME_20261007/N0065_ver_mutate.py <apply|restore|hash> <name>

Each mutation backs up the original file bytes next to this script before
changing it; restore writes the backup back byte-for-byte and checks the hash.
"""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent

MUTATIONS = {
    # Non-admin '*' / comma grant rows are accepted again.
    "star": (
        ROOT / "apps" / "api" / "app" / "core" / "product_line_scope.py",
        'if not line or line == "*" or "," in line:',
        "if not line:",
    ),
    # Every numeric user treated as admin (bypass for all roles).
    "alladmin": (
        ROOT / "apps" / "api" / "app" / "api" / "v1" / "router.py",
        'is_admin = user.get("role") == Role.ADMIN',
        "is_admin = True",
    ),
}


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def main() -> int:
    action, name = sys.argv[1], sys.argv[2]
    path, old, new = MUTATIONS[name]
    bak = HERE / f"N0065_ver_bak_{name}.bin"
    if action == "hash":
        print(path.name, sha(path))
        return 0
    if action == "apply":
        data = path.read_bytes()
        assert data.count(old.encode()) == 1, "anchor not found exactly once"
        bak.write_bytes(data)
        path.write_bytes(data.replace(old.encode(), new.encode()))
        print("applied", name, "orig", hashlib.sha256(data).hexdigest(), "now", sha(path))
        return 0
    if action == "restore":
        data = bak.read_bytes()
        path.write_bytes(data)
        assert sha(path) == hashlib.sha256(data).hexdigest()
        bak.unlink()
        print("restored", name, sha(path))
        return 0
    raise SystemExit("unknown action")


if __name__ == "__main__":
    raise SystemExit(main())
