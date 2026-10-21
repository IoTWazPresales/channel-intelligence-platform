"""N-0101 read-only Redis probe: site-pause keys and recent listing_capture.poll_listings results.

GET/SCAN only. Prints no URLs with credentials (only the db index of each URL).
"""
from __future__ import annotations

import json

import redis

from app.core.config import get_settings

s = get_settings()
pause = redis.Redis.from_url(s.redis_url, socket_connect_timeout=1)
print("pause keys:")
for k in pause.scan_iter(match="cip:listing_capture:site_pause:*"):
    print(" ", k.decode(), pause.ttl(k), pause.get(k).decode())

res = redis.Redis.from_url(s.celery_result_backend, socket_connect_timeout=1)
rows = []
for k in res.scan_iter(match="celery-task-meta-*", count=1000):
    raw = res.get(k)
    if not raw:
        continue
    try:
        d = json.loads(raw)
    except ValueError:
        continue
    if d.get("name") == "listing_capture.poll_listings" or (
        isinstance(d.get("result"), dict) and "polled" in d["result"]
    ):
        rows.append(d)
rows.sort(key=lambda d: str(d.get("date_done")))
print("poll results:", len(rows))
for d in rows[-5:]:
    print(json.dumps({"status": d.get("status"), "date_done": d.get("date_done"), "result": d.get("result")}, default=str))
