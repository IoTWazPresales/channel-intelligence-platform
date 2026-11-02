"""Read-only GETs against the local stack (API :8001, web :3000). Prints status codes and the on-the-water figures.

    apps/api/.venv/Scripts/python.exe -X utf8 .eif/audit/REVIEW_20261102/deploy/http_check.py [tag]
Writes .eif/audit/REVIEW_20261102/deploy/otw_<tag>.json (the on-the-water payload).
"""
import json
import sys
import urllib.error
import urllib.request

tag = sys.argv[1] if len(sys.argv) > 1 else "run"
API, WEB = "http://127.0.0.1:8001", "http://127.0.0.1:3000"


def get(url: str, timeout: int = 90):
    try:
        with urllib.request.urlopen(urllib.request.Request(url), timeout=timeout) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()
    except Exception as e:  # noqa: BLE001
        return type(e).__name__, str(e).encode()


for name, url in (("api /health/ready", API + "/health/ready"), ("web /login", WEB + "/login"), ("web /shipping/one", WEB + "/shipping/one"), ("web /supply/shipments", WEB + "/supply/shipments")):
    code, body = get(url)
    print(f"{name}: {code}" + (f" {body[:120].decode(errors='replace')}" if name.startswith("api") else ""))

code, body = get(API + "/api/v1/shipping/on-the-water")
print("api /api/v1/shipping/on-the-water:", code)
if code == 200:
    d = json.loads(body)
    open(f".eif/audit/REVIEW_20261102/deploy/otw_{tag}.json", "w", encoding="utf-8").write(json.dumps(d, indent=1, sort_keys=True, default=str))
    print("top-level keys:", sorted(d.keys()))
    for k in ("tiles", "kpis", "summary", "totals", "needs_look", "needs_a_look", "at_sea", "headline"):
        if k in d:
            print(k, "=", json.dumps(d[k], default=str)[:700])
else:
    print(body[:300])
