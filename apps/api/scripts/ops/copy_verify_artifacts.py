"""Copy browser VERIFY screenshots from Cursor temp into docs/verify/artifacts/."""
from __future__ import annotations

import shutil
from pathlib import Path

REPO = Path(__file__).resolve().parents[4]
DEST = REPO / "docs" / "verify" / "artifacts"
TEMP = Path.home() / "AppData" / "Local" / "Temp" / "cursor" / "screenshots"

NAMES = [
    "session-d-6f-before-accept.png",
    "session-d-6f-after-accept.png",
    "session-d-6f-after-soft-clear.png",
    "session-f-15b-before-compute.png",
    "session-f-15b-after-compute.png",
    "session-f-b4-dirty-before-refresh.png",
    "session-f-b4-dirty-after-refresh.png",
    "session-b-12-before-save.png",
    "session-b-12-after-reload.png",
    "page-2026-08-31T11-51-12-002Z.png",
    "page-2026-08-31T11-52-55-303Z.png",
]

# Also search nested docs path used by earlier captures
EXTRA_GLOBS = [
    "session-d-*.png",
    "session-f-*.png",
    "session-b-*.png",
    "page-2026-08-31*.png",
]


def main() -> int:
    DEST.mkdir(parents=True, exist_ok=True)
    copied: list[str] = []
    missing: list[str] = []

    search_roots = [TEMP, TEMP / "docs" / "verify" / "artifacts"]
    for name in NAMES:
        found = None
        for root in search_roots:
            candidate = root / name
            if candidate.is_file():
                found = candidate
                break
        if found is None:
            missing.append(name)
            continue
        target = DEST / name
        shutil.copy2(found, target)
        copied.append(name)

    for root in search_roots:
        if not root.is_dir():
            continue
        for pattern in EXTRA_GLOBS:
            for path in root.rglob(pattern):
                if path.name in copied:
                    continue
                target = DEST / path.name
                if not target.is_file():
                    shutil.copy2(path, target)
                    copied.append(path.name)

    print("dest", DEST)
    print("copied", len(copied))
    for n in sorted(set(copied)):
        print(" ", n)
    if missing:
        print("missing", len(missing))
        for n in missing:
            print(" ", n)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
