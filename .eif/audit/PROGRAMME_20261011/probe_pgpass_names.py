"""Find a local Postgres credential file by name. Do not print contents."""
from __future__ import annotations

import os
from pathlib import Path

home = Path(os.environ.get("USERPROFILE", ""))
names = [
    ".pgpass",
    "pgpass.conf",
    ".pg_service.conf",
]
roots = [
    home,
    home / "AppData" / "Roaming" / "postgresql",
    home / "AppData" / "Local" / "postgresql",
]
print("home_set", bool(home))
for root in roots:
    print("root_exists", root.name or "home", root.is_dir())
    if not root.is_dir():
        continue
    for name in names:
        path = root / name
        print("file", name, path.is_file(), path.stat().st_size if path.is_file() else 0)
