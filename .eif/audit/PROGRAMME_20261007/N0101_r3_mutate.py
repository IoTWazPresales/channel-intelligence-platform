"""N-0101 round 3 mutation M-S1 "always store the snapshot", or restore.

Usage (repo root, venv python):
  python N0101_r3_mutate.py apply    -> backs up registry.py, writes the mutant
  python N0101_r3_mutate.py restore  -> restores the backup and deletes it
"""

import hashlib
import pathlib
import shutil
import sys

ROOT = pathlib.Path(__file__).resolve().parents[3]
TARGET = ROOT / "apps/api/app/services/listing_capture/registry.py"
BACKUP = pathlib.Path(__file__).with_name("N0101_r3_registry.bak")

ORIGINAL = "    if snapshot_reason is None:\n        obs.raw_snapshot = None\n"
MUTANT = "    if False:  # MUTANT M-S1: always store the snapshot\n        obs.raw_snapshot = None\n"


def sha(p: pathlib.Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def main() -> None:
    mode = sys.argv[1]
    if mode == "apply":
        print("before", sha(TARGET))
        shutil.copy2(TARGET, BACKUP)
        s = TARGET.read_bytes().decode("utf-8")
        nl = "\r\n" if "\r\n" in s else "\n"
        orig, mut = ORIGINAL.replace("\n", nl), MUTANT.replace("\n", nl)
        assert s.count(orig) == 1, "anchor not found exactly once"
        TARGET.write_bytes(s.replace(orig, mut).encode("utf-8"))
        print("mutant", sha(TARGET))
    elif mode == "restore":
        shutil.copy2(BACKUP, TARGET)
        BACKUP.unlink()
        print("restored", sha(TARGET))
    else:
        raise SystemExit("apply|restore")


if __name__ == "__main__":
    main()
