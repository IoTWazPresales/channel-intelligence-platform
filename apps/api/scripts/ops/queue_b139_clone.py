"""Make cip_queue_b139 as a pg_dump copy of cip. Does not drop any database and does not write to cip."""
from __future__ import annotations

import sys
from pathlib import Path

WORKTREE_API = Path(__file__).resolve().parents[2]
MAIN_API = Path(__file__).resolve().parents[6] / "apps" / "api"
sys.path.insert(0, str(MAIN_API))
sys.path.insert(0, str(WORKTREE_API))

from app.core.config import get_settings  # noqa: E402
from scripts.ops.prove_job_delete_restore_clone import create_clone, db_name  # noqa: E402
from scripts.ops.prove_on_the_water_clone import admin_url  # noqa: E402

TARGET = "cip_queue_b139"


def main() -> int:
    settings = get_settings()
    source = db_name(settings.database_url_sync)
    print("source_database", source)
    if source != "cip":
        print("STOP: settings database is not cip")
        return 2
    create_clone(admin_url(settings), source, TARGET)
    print("clone_ready", TARGET)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
