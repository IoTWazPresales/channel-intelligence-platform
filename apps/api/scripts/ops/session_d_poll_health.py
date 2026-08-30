"""Poll GET /health/ready until ready or timeout. Prints body. No writes."""
from __future__ import annotations

import json
import sys
import time
import urllib.request

API = "http://127.0.0.1:8001"


def main() -> int:
    deadline = time.time() + 80
    last = None
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(f"{API}/health/ready", timeout=4) as r:
                body = r.read().decode("utf-8", errors="replace")
                print("HTTP", r.status)
                print(body)
                parsed = json.loads(body)
                print("database", parsed.get("database"))
                return 0
        except Exception as exc:
            last = f"{type(exc).__name__}: {exc}"
            time.sleep(2)
    print("TIMEOUT", last)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
