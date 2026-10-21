"""N-0101 round 2 mutation M-D1: put back the swallowed import error, or restore.

Usage (repo root, venv python):
  python N0101_r2_mutate.py apply    -> backs up site_pause.py, writes the mutant
  python N0101_r2_mutate.py restore  -> restores the backup and deletes it
"""

import hashlib
import pathlib
import shutil
import sys

ROOT = pathlib.Path(__file__).resolve().parents[3]
TARGET = ROOT / "apps/api/app/services/listing_capture/site_pause.py"
BACKUP = pathlib.Path(__file__).with_name("N0101_r2_site_pause.bak")

MUTANT = '''def default_site_pause_store() -> SitePauseStore:
    """MUTANT M-D1: the original swallowed import error."""
    try:
        from app.core.config import settings

        client = redis.Redis.from_url(settings.redis_url, socket_connect_timeout=0.5, socket_timeout=2)
        client.ping()
        return RedisSitePauseStore(client)
    except Exception:  # noqa: BLE001
        logger.warning("listing capture: Redis unavailable; site pauses kept in this process only")
        return _memory_store


'''


def sha(p: pathlib.Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def main() -> None:
    mode = sys.argv[1]
    if mode == "apply":
        print("before", sha(TARGET))
        shutil.copy2(TARGET, BACKUP)
        s = TARGET.read_text(encoding="utf-8")
        start = s.index("def default_site_pause_store()")
        end = s.index("def _parse_until(")
        TARGET.write_text(s[:start] + MUTANT + s[end:], encoding="utf-8", newline="")
        print("mutant", sha(TARGET))
    elif mode == "restore":
        shutil.copy2(BACKUP, TARGET)
        BACKUP.unlink()
        print("restored", sha(TARGET))
    else:
        raise SystemExit("apply|restore")


if __name__ == "__main__":
    main()
