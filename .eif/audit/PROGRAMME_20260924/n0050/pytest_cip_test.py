"""N-0048: run pytest with DATABASE_URL(_SYNC) pointed at cip_test (never prints the URL)."""
import os
import sys
from urllib.parse import urlparse, urlunparse

API = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", "..", "apps", "api")
API = os.path.abspath(API)
sys.path.insert(0, API)
os.chdir(API)
from app.core.config import get_settings  # noqa: E402

s = get_settings()


def swap(u: str) -> str:
    return urlunparse(urlparse(u)._replace(path="/cip_test"))


os.environ["DATABASE_URL"] = swap(s.database_url)
os.environ["DATABASE_URL_SYNC"] = swap(s.database_url_sync)
if hasattr(get_settings, "cache_clear"):
    get_settings.cache_clear()
print("pytest DB ->", urlparse(get_settings().database_url_sync).path)
import pytest  # noqa: E402

sys.exit(pytest.main(sys.argv[1:]))
