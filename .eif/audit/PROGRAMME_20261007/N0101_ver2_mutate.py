"""GOV-008 RUN-20261008-N0101-VER2 mutation helper (temporary product edit, always restored).

usage: python N0101_ver2_mutate.py apply <variant> | restore | hash
variants:
  A  swallowed import error: the client is built inside the try from the non-existent
     ``app.core.config.settings`` and ImportError is added to the "unreachable" tuple.
  B  broad swallow: the except catches Exception (any code error reads as an outage).
"""

from __future__ import annotations

import hashlib
import pathlib
import shutil
import sys

ROOT = pathlib.Path(__file__).resolve().parents[3]
TARGET = ROOT / "apps" / "api" / "app" / "services" / "listing_capture" / "site_pause.py"
BACKUP = pathlib.Path(__file__).with_name("N0101_ver2_site_pause.bak")


def sha(p: pathlib.Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def sub(text: str, old: str, new: str) -> str:
    if text.count(old) != 1:
        raise SystemExit(f"anchor not unique/found: {old!r}")
    return text.replace(old, new)


def apply(variant: str) -> None:
    if BACKUP.exists():
        raise SystemExit("backup already exists; restore first")
    shutil.copy2(TARGET, BACKUP)
    text = TARGET.read_text(encoding="utf-8")
    if variant == "A":
        text = sub(
            text,
            "    return redis.Redis.from_url(get_settings().redis_url, socket_connect_timeout=0.5, socket_timeout=2)",
            "    from app.core.config import settings  # MUTANT-VER2-A\n"
            "    return redis.Redis.from_url(settings.redis_url, socket_connect_timeout=0.5, socket_timeout=2)",
        )
        text = sub(
            text,
            "    client = _redis_client()\n    try:\n        client.ping()",
            "    try:\n        client = _redis_client()  # MUTANT-VER2-A\n        client.ping()",
        )
        text = sub(text, "    OSError,\n)", "    OSError,\n    ImportError,  # MUTANT-VER2-A\n)")
    elif variant == "B":
        text = sub(
            text,
            "    except _REDIS_UNREACHABLE_ERRORS as exc:",
            "    except Exception as exc:  # MUTANT-VER2-B",
        )
    else:
        raise SystemExit("unknown variant")
    TARGET.write_text(text, encoding="utf-8")
    print("applied", variant, "sha256", sha(TARGET))


def restore() -> None:
    shutil.copy2(BACKUP, TARGET)
    BACKUP.unlink()
    print("restored sha256", sha(TARGET), "MUTANT count", TARGET.read_text(encoding="utf-8").count("MUTANT"))


if __name__ == "__main__":
    cmd = sys.argv[1]
    if cmd == "apply":
        apply(sys.argv[2])
    elif cmd == "restore":
        restore()
    else:
        print("sha256", sha(TARGET))
