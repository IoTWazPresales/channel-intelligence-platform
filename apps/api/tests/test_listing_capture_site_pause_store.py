"""N-0101 round 2 (GOV-008 defect D1): which store ``default_site_pause_store`` picks.

The first build hid an ImportError behind ``except Exception`` and always returned the
process-local store. These tests pin: Redis is used when its client answers, the local
store only when Redis is unreachable (with one warning), and code errors are raised.
No real Redis is contacted: ``redis.Redis.from_url`` is replaced by a fake.
"""

from __future__ import annotations

import logging

import pytest
import redis

from app.core.config import get_settings
from app.services.listing_capture import site_pause
from app.services.listing_capture.site_pause import (
    MemorySitePauseStore,
    RedisSitePauseStore,
    default_site_pause_store,
)

LOGGER_NAME = "app.services.listing_capture.site_pause"


class _FakeRedis:
    def __init__(self, ping_error: BaseException | None = None) -> None:
        self.ping_error = ping_error
        self.pings = 0
        self.data: dict[str, str] = {}

    def ping(self) -> bool:
        self.pings += 1
        if self.ping_error is not None:
            raise self.ping_error
        return True

    def get(self, key: str):
        return self.data.get(key)

    def set(self, key: str, value: str, ex: int | None = None) -> None:
        self.data[key] = value

    def delete(self, key: str) -> None:
        self.data.pop(key, None)


@pytest.fixture
def fake_from_url(monkeypatch):
    """Replace ``redis.Redis.from_url``; returns the list of (url, kwargs) calls and the client."""
    calls: list[tuple[str, dict]] = []
    holder: dict[str, _FakeRedis] = {"client": _FakeRedis()}

    def _from_url(url, **kwargs):
        calls.append((url, kwargs))
        return holder["client"]

    monkeypatch.setattr(redis.Redis, "from_url", staticmethod(_from_url))
    monkeypatch.setattr(site_pause, "_fallback_warned", False)
    return calls, holder


def test_uses_redis_when_the_client_answers(fake_from_url, caplog):
    calls, holder = fake_from_url
    with caplog.at_level(logging.WARNING, logger=LOGGER_NAME):
        store = default_site_pause_store()

    assert isinstance(store, RedisSitePauseStore), "a reachable Redis must not fall back to the local store"
    assert not isinstance(store, MemorySitePauseStore)
    assert holder["client"].pings == 1
    assert calls and calls[0][0] == get_settings().redis_url
    assert not [r for r in caplog.records if r.name == LOGGER_NAME]


def test_redis_store_round_trips_the_pause_record(fake_from_url):
    _, holder = fake_from_url
    store = default_site_pause_store()
    record = {"marketplace": "takealot", "hours": 1, "until": "2026-10-08T10:00:00+00:00"}
    store.set("takealot", record, ttl_seconds=25 * 3600)

    assert site_pause.KEY_PREFIX + "takealot" in holder["client"].data
    assert store.get("takealot") == record
    store.delete("takealot")
    assert store.get("takealot") is None


@pytest.mark.parametrize(
    "error",
    [
        redis.exceptions.ConnectionError("Error 10061 connecting to localhost:6379."),
        redis.exceptions.TimeoutError("Timeout connecting to server"),
        OSError("network unreachable"),
    ],
    ids=["connection_refused", "timeout", "os_error"],
)
def test_falls_back_only_when_unreachable_and_logs_once(fake_from_url, caplog, error):
    _, holder = fake_from_url
    holder["client"] = _FakeRedis(ping_error=error)

    with caplog.at_level(logging.WARNING, logger=LOGGER_NAME):
        first = default_site_pause_store()
        second = default_site_pause_store()

    assert isinstance(first, MemorySitePauseStore)
    assert second is first  # the one process-local store, so pauses persist across runs
    warnings = [r for r in caplog.records if r.name == LOGGER_NAME and r.levelno == logging.WARNING]
    assert len(warnings) == 1, "the fallback must be logged, and only once per outage"
    message = warnings[0].getMessage()
    assert "unreachable" in message and type(error).__name__ in message


def test_warns_again_after_redis_comes_back_and_drops_again(fake_from_url, caplog):
    _, holder = fake_from_url
    down = _FakeRedis(ping_error=redis.exceptions.ConnectionError("refused"))
    with caplog.at_level(logging.WARNING, logger=LOGGER_NAME):
        holder["client"] = down
        default_site_pause_store()
        holder["client"] = _FakeRedis()
        assert isinstance(default_site_pause_store(), RedisSitePauseStore)
        holder["client"] = down
        assert isinstance(default_site_pause_store(), MemorySitePauseStore)

    messages = [r.getMessage() for r in caplog.records if r.name == LOGGER_NAME]
    assert sum("unreachable" in m for m in messages) == 2
    assert sum("reachable again" in m for m in messages) == 1


@pytest.mark.parametrize(
    "error",
    [AttributeError("no such attribute"), ImportError("cannot import name"), redis.exceptions.ResponseError("bad")],
    ids=["attribute_error", "import_error", "response_error"],
)
def test_code_errors_are_raised_not_hidden_as_an_outage(fake_from_url, caplog, error):
    _, holder = fake_from_url
    holder["client"] = _FakeRedis(ping_error=error)

    with caplog.at_level(logging.WARNING, logger=LOGGER_NAME), pytest.raises(type(error)):
        default_site_pause_store()
    assert not [r for r in caplog.records if r.name == LOGGER_NAME]
