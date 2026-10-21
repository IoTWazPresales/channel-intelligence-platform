"""N-0110 repair: make or drop a clone of cip (pg_dump/pg_restore as the admin role).

usage: python clone.py make <clone>   |   python clone.py drop <clone>
Passwords are never printed. Only names starting with cip_n0110 are accepted.
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "n0110"))

from clone_proof import PG_BIN, admin_exec, pg_env  # noqa: E402


def main() -> int:
    action, name = sys.argv[1], sys.argv[2]
    if not name.startswith("cip_n0110"):
        raise SystemExit("clone name must start with cip_n0110")
    admin_exec(f"DROP DATABASE IF EXISTS {name}")
    if action == "drop":
        return 0
    admin_exec(f"CREATE DATABASE {name} OWNER cip")
    env = pg_env()
    with tempfile.TemporaryDirectory() as tmp:
        dump = Path(tmp) / "cip.dump"
        subprocess.run([str(PG_BIN / "pg_dump"), "-Fc", "-d", "cip", "-f", str(dump)], env=env, check=True)
        subprocess.run([str(PG_BIN / "pg_restore"), "-d", name, str(dump)], env=env, check=False)
    print(f"clone {name} made from cip", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
