"""GOV-008 RUN-20261008-N0101-VER3 mutation helper (temporary product edit, always restored).

usage: python N0101_ver3_mutate.py apply <variant> | restore | hash
variants:
  A  "previous observation of ANY status": previous_successful_observation() loses its
     http_status == 200 and parse_status == 'ok' filters (registry.py).
  B  retention deletes rows: the clear statement becomes a DELETE (snapshot_retention.py).
  C  retention ignores the 90-day cutoff (snapshot_retention.py).
"""

from __future__ import annotations

import hashlib
import pathlib
import shutil
import sys

ROOT = pathlib.Path(__file__).resolve().parents[3]
LC = ROOT / "apps" / "api" / "app" / "services" / "listing_capture"
TARGETS = {"A": LC / "registry.py", "B": LC / "snapshot_retention.py", "C": LC / "snapshot_retention.py"}
STATE = pathlib.Path(__file__).with_name("N0101_ver3_state.txt")


def sha(p: pathlib.Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def sub(text: str, old: str, new: str) -> str:
    if text.count(old) != 1:
        raise SystemExit(f"anchor not unique/found: {old!r}")
    return text.replace(old, new)


def backup_of(target: pathlib.Path) -> pathlib.Path:
    return pathlib.Path(__file__).with_name(f"N0101_ver3_{target.name}.bak")


def apply(variant: str) -> None:
    if STATE.exists():
        raise SystemExit("a mutant is already applied; restore first")
    target = TARGETS[variant]
    bak = backup_of(target)
    shutil.copy2(target, bak)
    STATE.write_text(variant, encoding="utf-8")
    text = target.read_text(encoding="utf-8")
    if variant == "A":
        text = sub(
            text,
            "            ListingObservation.listing_id == listing_id,\n"
            "            ListingObservation.http_status == 200,\n"
            "            ListingObservation.parse_status == \"ok\",\n",
            "            ListingObservation.listing_id == listing_id,  # MUTANT-VER3-A\n",
        )
    elif variant == "B":
        text = sub(
            text,
            "    UPDATE listing_observation\n    SET raw_snapshot = NULL,",
            "    DELETE FROM listing_observation WHERE id = ANY(:ids) AND CAST(:days AS integer) > 0\n"
            "      AND CAST(:cleared_at AS text) IS NOT NULL  -- MUTANT-VER3-B\n"
            "    \"\"\"\n)\n_UNUSED = text(\n    \"\"\"\n    UPDATE listing_observation\n    SET raw_snapshot = NULL,",
        )
        # The original _CLEAR_BATCH name now points at the DELETE (first definition), the
        # UPDATE text is kept under _UNUSED so the module still parses.
    elif variant == "C":
        text = sub(
            text,
            "      AND fetched_at < :cutoff\n",
            "      AND (fetched_at < :cutoff OR TRUE)  -- MUTANT-VER3-C\n",
        )
    else:
        raise SystemExit("unknown variant")
    target.write_text(text, encoding="utf-8")
    print("applied", variant, target.name, "sha256", sha(target)[:16])


def restore() -> None:
    variant = STATE.read_text(encoding="utf-8").strip()
    target = TARGETS[variant]
    bak = backup_of(target)
    shutil.copy2(bak, target)
    bak.unlink()
    STATE.unlink()
    print("restored", variant, target.name, "sha256", sha(target)[:16],
          "MUTANT count", target.read_text(encoding="utf-8").count("MUTANT"))


if __name__ == "__main__":
    cmd = sys.argv[1]
    if cmd == "apply":
        apply(sys.argv[2])
    elif cmd == "restore":
        restore()
    else:
        for p in sorted(set(TARGETS.values())):
            print(p.name, "sha256", sha(p)[:16])
