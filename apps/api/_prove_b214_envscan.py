"""Find local env files that name a database URL. Prints paths and key presence only."""

import os
from pathlib import Path

root = Path(r"C:\Users\warren_eliason\channel-intelligence-platform")
skip = {".git", "node_modules", ".venv", "__pycache__"}
paths = []
for dirpath, dirnames, filenames in os.walk(root):
    dirnames[:] = [name for name in dirnames if name not in skip]
    for filename in filenames:
        if filename.startswith(".env"):
            paths.append(Path(dirpath) / filename)
for path in paths:
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except OSError as exc:
        print("unreadable", path, type(exc).__name__)
        continue
    keys = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key = stripped.split("=", 1)[0].strip()
        if "DATABASE" in key or key.startswith("POSTGRES"):
            keys.append(key)
    if keys:
        print(path.relative_to(root), keys)
