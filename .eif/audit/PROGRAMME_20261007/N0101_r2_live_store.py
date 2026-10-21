"""N-0101 round 2 live check (read-only): which store default_site_pause_store() returns.

Run from apps/api with the venv python. Writes nothing to Redis: it only pings, reads the
connection's db index and counts existing site-pause keys. Prints no URL or secret.
"""

import logging

logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s %(message)s")

from app.services.listing_capture import site_pause  # noqa: E402

store = site_pause.default_site_pause_store()
print("store_type", type(store).__name__)
if isinstance(store, site_pause.RedisSitePauseStore):
    client = store._client
    kw = client.connection_pool.connection_kwargs
    print("redis_host", kw.get("host"), "port", kw.get("port"), "db", kw.get("db"))
    keys = list(client.scan_iter(match=site_pause.KEY_PREFIX + "*", count=100))
    print("site_pause_keys", len(keys))
    for marketplace in ("amazon", "evetech", "takealot"):
        print("get", marketplace, store.get(marketplace))
