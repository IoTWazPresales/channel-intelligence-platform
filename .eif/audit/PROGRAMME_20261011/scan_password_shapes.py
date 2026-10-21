"""Report password-shaped assignments. Never print values."""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SKIP = {".git", "node_modules", ".venv", "__pycache__", ".next", "dist"}
KEY_RE = re.compile(r"(PASSWORD|APP_PASSWORD|SECRET|PASSWD)", re.I)
APP_RE = re.compile(r"(?<![A-Za-z0-9])([a-z]{4} [a-z]{4} [a-z]{4} [a-z]{4}|[a-z]{16})(?![A-Za-z0-9])")


def shape_of(value: str) -> str:
    compact = value.replace(" ", "")
    if not compact:
        return "empty"
    if re.fullmatch(r"[a-z]{16}", compact):
        return "gmail_app_password_shape"
    if re.fullmatch(r"[A-Za-z0-9]{16}", compact):
        return "16_alnum"
    punct = any(not ch.isalnum() for ch in compact)
    return f"other_len_{len(compact)}_punct_{punct}"


def main() -> None:
    hits = 0
    for path in ROOT.rglob("*"):
        if not path.is_file():
            continue
        if any(part in SKIP for part in path.parts):
            continue
        if path.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp", ".gif", ".pdf", ".woff", ".woff2", ".ico"}:
            continue
        try:
            if path.stat().st_size > 2_000_000:
                continue
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        rel = path.relative_to(ROOT).as_posix()
        for i, line in enumerate(text.splitlines(), 1):
            if KEY_RE.search(line) and ("=" in line or ":" in line):
                raw = line.split("=", 1)[-1].strip().strip('"').strip("'")
                key = line.split("=", 1)[0].strip().lstrip("#").strip()[:80]
                print(f"{rel}:{i} key={key} shape={shape_of(raw)} present={bool(raw)}")
                hits += 1
            if APP_RE.search(line) and "PASSWORD" not in line.upper():
                print(f"{rel}:{i} key=bare_16 shape=gmail_app_password_shape present=True")
                hits += 1
    print("hit_count", hits)


if __name__ == "__main__":
    main()
