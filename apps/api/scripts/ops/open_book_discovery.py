"""Run the read-only open-book census and write discovery.txt. Never writes to the database."""

from __future__ import annotations

import runpy
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
AUDIT = ROOT / ".eif" / "audit" / "OPEN_BOOK_20261028"
SCRIPT = AUDIT / "discover_open_book.py"
OUT = AUDIT / "discovery.txt"


class _Tee:
    def __init__(self, *streams):
        self.streams = streams

    def write(self, data: str) -> int:
        for stream in self.streams:
            stream.write(data)
        return len(data)

    def flush(self) -> None:
        for stream in self.streams:
            stream.flush()


def _readers(root: Path) -> str:
    lines: list[str] = ["", "=== readers of open_order or line_state under apps/api ==="]
    api = root / "apps" / "api"
    hits = 0
    for path in sorted(api.rglob("*.py")):
        if any(part in {".venv", "__pycache__"} for part in path.parts):
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        rel = path.relative_to(root).as_posix()
        for number, line in enumerate(text.splitlines(), start=1):
            if "open_order" in line or "line_state" in line:
                hits += 1
                lines.append(f"{rel}:{number}: {line.strip()}")
    lines.append(f"reader_hit_lines={hits}")
    return "\n".join(lines) + "\n"


def main() -> None:
    AUDIT.mkdir(parents=True, exist_ok=True)
    buf = OUT.open("w", encoding="utf-8")
    old = sys.stdout
    sys.stdout = _Tee(old, buf)
    try:
        sys.argv = [str(SCRIPT), "cip"]
        runpy.run_path(str(SCRIPT), run_name="__main__")
        print(_readers(ROOT), end="")
    finally:
        sys.stdout = old
        buf.close()
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
