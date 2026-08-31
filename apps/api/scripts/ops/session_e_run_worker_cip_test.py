"""Start Celery worker with DATABASE_* rewritten to cip_test (SESSION E / S11 proof only)."""
from __future__ import annotations

import os
import sys
from pathlib import Path

API_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(API_ROOT))
os.chdir(API_ROOT)

from session_d_run_api import apply_mode  # noqa: E402

if __name__ == "__main__":
    apply_mode("cip_test")
    from celery.__main__ import main as celery_main  # noqa: E402

    sys.argv = [
        "celery",
        "-A",
        "app.worker.celery_app",
        "worker",
        "-l",
        "info",
        "-Q",
        "interactive,batch,celery",
        "--pool=solo",
    ]
    celery_main()
