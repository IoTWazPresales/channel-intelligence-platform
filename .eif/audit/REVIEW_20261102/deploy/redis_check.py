"""READ-ONLY redis check before/after a worker restart: queue length, unacked messages, celery ping.

    apps/api/.venv/Scripts/python.exe -X utf8 .eif/audit/REVIEW_20261102/deploy/redis_check.py
"""
import sys

sys.path.insert(0, "apps/api")

import redis  # noqa: E402

from app.core.config import get_settings  # noqa: E402

s = get_settings()
url = next((getattr(s, a) for a in ("celery_broker_url", "redis_url", "broker_url") if getattr(s, a, None)), None)
print("broker settings attr found:", bool(url))
r = redis.Redis.from_url(url, socket_timeout=5)
print("PING:", r.ping())
print("llen celery:", r.llen("celery"))
for k in ("unacked", "unacked_index"):
    t = r.type(k).decode()
    n = r.hlen(k) if t == "hash" else (r.zcard(k) if t == "zset" else 0)
    print(f"{k}: type={t} size={n}")
print("keys (count):", r.dbsize())

try:
    from app.worker.celery_app import celery_app  # noqa: E402
except Exception:  # noqa: BLE001
    try:
        from app.core.celery_app import celery_app  # noqa: E402
    except Exception as e:  # noqa: BLE001
        celery_app = None
        print("celery app import failed:", type(e).__name__)
if celery_app is not None:
    print("celery ping:", celery_app.control.ping(timeout=5))
