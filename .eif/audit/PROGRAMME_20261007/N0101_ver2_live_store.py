"""GOV-008 RUN-20261008-N0101-VER2: read-only live store check (ping, scan, get; no write).

Run with the API venv python from apps/api. Prints no URL, password or secret.
"""

from __future__ import annotations

import logging
import time

logging.basicConfig(level=logging.WARNING)

from app.services.listing_capture import site_pause  # noqa: E402

t0 = time.perf_counter()
store = site_pause.default_site_pause_store()
elapsed = time.perf_counter() - t0
print("store_type", type(store).__name__, f"selected_in_s {elapsed:.3f}")
if isinstance(store, site_pause.RedisSitePauseStore):
    client = store._client  # noqa: SLF001
    kw = client.connection_pool.connection_kwargs
    print("redis host", kw.get("host"), "port", kw.get("port"), "db", kw.get("db"))
    keys = list(client.scan_iter(match=site_pause.KEY_PREFIX + "*", count=500))
    print("site_pause_keys", len(keys))
    for mkt in ("amazon", "evetech", "takealot"):
        print("get", mkt, store.get(mkt))
print("fallback_warned", site_pause._fallback_warned)  # noqa: SLF001
