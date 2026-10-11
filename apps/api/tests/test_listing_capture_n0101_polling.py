"""N-0101 (N-0085 U1): restock, out_of_stock polled, dead-link back-off, per-site
403/429 pause, run time limit, per-site spacing, ordinary browser User-Agent.

No DB and no network: MagicMock session, injected http_get / clock / sleep / store.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

from sqlalchemy.dialects import postgresql

from app.services.listing_capture import observation as obs_mod
from app.services.listing_capture.observation import LISTING_CAPTURE_USER_AGENT
from app.services.listing_capture.registry import (
    POLLED_LISTING_STATUSES,
    _interleave_by_marketplace,
    listing_consecutive_failures,
    listing_in_dead_link_backoff,
    poll_active_listings,
    record_observation,
)
from app.services.listing_capture.site_pause import (
    MemorySitePauseStore,
    pause_site,
    paused_until,
)

IN_STOCK = '{"price": 999.0, "availability": "in_stock"}'
OUT_OF_STOCK = '{"price": 999.0, "availability": "out_of_stock"}'


def _listing(lid: int, marketplace: str = "evetech", status: str = "active", **kw):
    return SimpleNamespace(
        id=lid,
        url=kw.pop("url", f"https://example.test/{marketplace}/{lid}"),
        marketplace=marketplace,
        status=status,
        status_observed_at=kw.pop("status_observed_at", None),
        meta_json=kw.pop("meta_json", None),
        product_id=kw.pop("product_id", None),
        external_id=kw.pop("external_id", None),
    )


def _session(listings):
    session = MagicMock()
    session.scalars.return_value.all.return_value = list(listings)
    return session


class FakeClock:
    def __init__(self) -> None:
        self.t = 1000.0
        self.sleeps: list[float] = []

    def __call__(self) -> float:
        return self.t

    def sleep(self, s: float) -> None:
        self.sleeps.append(s)
        self.t += s


def _poll(session, http_get, *, store=None, clock=None, **kw):
    clock = clock or FakeClock()
    return poll_active_listings(
        session,
        http_get=http_get,
        pause_store=store if store is not None else MemorySitePauseStore(),
        clock=clock,
        sleep=clock.sleep,
        **kw,
    )


# ---------------------------------------------------------------- restock / statuses


def test_out_of_stock_seen_in_stock_returns_to_active_as_restocked() -> None:
    listing = _listing(1, status="out_of_stock")
    obs = record_observation(MagicMock(), listing, http_get=lambda _u: (200, IN_STOCK))
    assert listing.status == "active"
    assert obs.parse_flags["status_transition"] == {
        "from": "out_of_stock",
        "to": "active",
        "reason": "restocked",
    }
    assert listing.status_observed_at == obs.fetched_at


def test_out_of_stock_unknown_availability_is_not_a_restock() -> None:
    listing = _listing(1, status="out_of_stock")
    obs = record_observation(
        MagicMock(), listing, http_get=lambda _u: (200, '{"price": 999.0, "availability": "unknown"}')
    )
    assert listing.status == "out_of_stock"
    assert "status_transition" not in obs.parse_flags


def test_active_going_out_of_stock_records_transition_and_staying_active_does_not() -> None:
    listing = _listing(1)
    obs = record_observation(MagicMock(), listing, http_get=lambda _u: (200, OUT_OF_STOCK))
    assert listing.status == "out_of_stock"
    assert obs.parse_flags["status_transition"]["reason"] == "out_of_stock"
    listing2 = _listing(2)
    obs2 = record_observation(MagicMock(), listing2, http_get=lambda _u: (200, IN_STOCK))
    assert listing2.status == "active"
    assert "status_transition" not in obs2.parse_flags


def test_poller_selects_out_of_stock_and_dead_link_oldest_due_first() -> None:
    session = _session([])
    _poll(session, lambda _u: (200, IN_STOCK))
    stmt = session.scalars.call_args.args[0]
    sql = str(stmt.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}))
    assert set(POLLED_LISTING_STATUSES) == {"active", "out_of_stock", "dead_link"}
    for st in POLLED_LISTING_STATUSES:
        assert f"'{st}'" in sql
    assert "max(listing_observation.fetched_at)" in sql
    assert "NULLS FIRST" in sql
    assert "'skipped'" in sql  # a back-off placeholder row is not a real check


def test_poller_polls_out_of_stock_listing() -> None:
    listing = _listing(5, status="out_of_stock")
    calls: list[str] = []

    def http_get(url):
        calls.append(url)
        return 200, OUT_OF_STOCK

    out = _poll(_session([listing]), http_get)
    assert out["polled"] == 1
    assert calls == [listing.url]
    assert listing.status == "out_of_stock"


# ---------------------------------------------------------------- dead-link back-off


def test_consecutive_dead_results_drive_backoff_and_a_good_parse_resets() -> None:
    listing = _listing(7)
    for n in (1, 2, 3):
        record_observation(MagicMock(), listing, http_get=lambda _u: (404, ""))
        assert listing.status == "dead_link"
        assert listing_consecutive_failures(listing) == n
    now = datetime.now(timezone.utc)
    assert listing_in_dead_link_backoff(listing, now=now) is True
    assert listing_in_dead_link_backoff(listing, now=now + timedelta(hours=25)) is False

    # The poller skips it without a request or a row while in back-off.
    calls: list[str] = []
    session = _session([listing])
    out = _poll(session, lambda u: calls.append(u) or (200, IN_STOCK))
    assert out["skipped_backoff"] == 1 and out["polled"] == 0 and calls == []
    session.add.assert_not_called()

    # A day later it is checked again; a good page brings it back and clears the count.
    out = _poll(_session([listing]), lambda _u: (200, IN_STOCK), now=now + timedelta(hours=25))
    assert out["polled"] == 1
    assert listing.status == "active"
    assert listing_consecutive_failures(listing) == 0
    assert "last_failure_at" not in (listing.meta_json or {})


def test_dead_link_with_two_failures_is_still_polled() -> None:
    listing = _listing(8, status="dead_link")
    record_observation(MagicMock(), listing, http_get=lambda _u: (404, ""))
    record_observation(MagicMock(), listing, http_get=lambda _u: (404, ""))
    assert listing_in_dead_link_backoff(listing) is False
    obs = record_observation(MagicMock(), listing, http_get=lambda _u: (200, IN_STOCK))
    assert listing.status == "active"
    assert obs.parse_flags["status_transition"]["reason"] == "link_recovered"


# ---------------------------------------------------------------- 403 / 429 site pause


def test_429_pauses_only_that_site_and_is_recorded() -> None:
    a1, a2, a3 = (_listing(i, "amazon") for i in (1, 2, 3))
    e1, e2 = (_listing(i, "evetech") for i in (11, 12))
    calls: list[str] = []

    def http_get(url):
        calls.append(url)
        if "/amazon/" in url:
            return 429, "<html>Too many requests R 12 999</html>"
        return 200, IN_STOCK

    store = MemorySitePauseStore()
    session = _session([a1, a2, a3, e1, e2])
    added: list = []
    session.add.side_effect = added.append
    out = _poll(session, http_get, store=store)

    assert sum("/amazon/" in c for c in calls) == 1  # no more requests to amazon this run
    assert sum("/evetech/" in c for c in calls) == 2  # evetech unaffected
    assert out["skipped_paused"] == {"amazon": 2}
    assert out["paused_sites"]["amazon"]["hours"] == 1
    assert out["paused_sites"]["amazon"]["http_status"] == 429
    assert "evetech" not in out["paused_sites"]
    refused_obs = [o for o in added if getattr(o, "http_status", None) == 429]
    assert len(refused_obs) == 1
    assert refused_obs[0].parse_flags["site_paused"]["hours"] == 1
    assert refused_obs[0].extracted_price is None  # never a price from a refusal page
    assert a1.status == "active"  # a refusal is not a dead link

    # Next run inside the pause: amazon is not contacted at all.
    calls.clear()
    out2 = _poll(_session([a1, e1]), http_get, store=store)
    assert [c for c in calls if "/amazon/" in c] == []
    assert out2["skipped_paused"] == {"amazon": 1}
    assert out2["paused_sites"]["amazon"]["paused_this_run"] is False


def test_403_pause_doubles_up_to_24h_and_clears_on_success() -> None:
    store = MemorySitePauseStore()
    now = datetime(2026, 10, 7, 12, 0, tzinfo=timezone.utc)
    hours = []
    for _ in range(7):
        rec = pause_site(store, "evetech", http_status=403, now=now)
        hours.append(rec["hours"])
    assert hours == [1, 2, 4, 8, 16, 24, 24]
    assert paused_until(store, "evetech", now=now) is not None
    assert paused_until(store, "evetech", now=now + timedelta(hours=25)) is None

    # After the pause ends, a 200 from the site clears the memory (next refusal is 1 h again).
    listing = _listing(1, "evetech")
    _poll(_session([listing]), lambda _u: (200, IN_STOCK), store=store, now=now + timedelta(hours=25))
    assert store.get("evetech") is None
    assert pause_site(store, "evetech", http_status=403, now=now)["hours"] == 1


def test_takealot_refusal_sends_no_follow_up_requests() -> None:
    session = _session([])
    session.get.return_value = SimpleNamespace(ean="6001234567890", upc=None)
    listing = _listing(
        3, "takealot", url="https://www.takealot.com/x/PLID12345678", product_id=99, meta_json={}
    )
    session.scalars.return_value.all.return_value = [listing]
    calls: list[str] = []

    def http_get(url):
        calls.append(url)
        return 429, ""

    out = _poll(session, http_get)
    assert len(calls) == 1  # details call only; the EAN search is not sent
    assert out["paused_sites"]["takealot"]["http_status"] == 429


# ---------------------------------------------------------------- run limit, mix, spacing


def test_run_stops_at_time_limit() -> None:
    listings = [_listing(i, "evetech" if i % 2 else "amazon") for i in range(10)]
    clock = FakeClock()

    def http_get(_url):
        clock.t += 100.0
        return 200, IN_STOCK

    out = _poll(_session(listings), http_get, clock=clock, time_limit_seconds=250)
    assert out["polled"] == 3
    assert out["stopped_reason"] == "time_limit"
    assert out["duration_seconds"] >= 250


def test_default_time_limit_is_ten_minutes() -> None:
    assert obs_mod.POLL_RUN_TIME_LIMIT_SECONDS == 600


def test_interleave_mixes_retailers_keeping_oldest_due_order() -> None:
    t1, t2, t3 = (_listing(i, "takealot") for i in (1, 2, 3))
    e1, e2 = (_listing(i, "evetech") for i in (4, 5))
    a1 = _listing(6, "amazon")
    got = [x.id for x in _interleave_by_marketplace([t1, t2, t3, e1, e2, a1])]
    assert got == [1, 4, 6, 2, 5, 3]


def test_spacing_is_per_site() -> None:
    clock = FakeClock()
    listings = [_listing(1, "evetech"), _listing(2, "evetech")]

    def http_get(_url):
        clock.t += 0.5
        return 200, IN_STOCK

    _poll(_session(listings), http_get, clock=clock)
    # Spacing runs from the end of the previous request to the same site.
    assert clock.sleeps == [obs_mod.RATE_LIMIT_SECONDS["evetech"]]

    # Alternating sites that each took longer than their spacing: no sleep.
    clock2 = FakeClock()

    def slow_get(_url):
        clock2.t += 2.5
        return 200, IN_STOCK

    _poll(_session([_listing(1, "evetech"), _listing(2, "amazon"), _listing(3, "evetech")]), slow_get, clock=clock2)
    assert clock2.sleeps == []


# ---------------------------------------------------------------- User-Agent (D-0063)


def test_user_agent_is_an_ordinary_browser_not_cip() -> None:
    ua = LISTING_CAPTURE_USER_AGENT
    assert ua.startswith("Mozilla/5.0 (")
    assert "Chrome/" in ua and "Safari/" in ua
    for token in ("cip", "listing-capture", "bot", "crawler", "spider", "python", "urllib"):
        assert token not in ua.lower()


def test_default_http_get_sends_browser_user_agent(monkeypatch) -> None:
    seen = {}

    class _Resp:
        status = 200

        def read(self):
            return b"ok"

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def fake_urlopen(request, timeout=None):
        seen["ua"] = request.get_header("User-agent")
        seen["lang"] = request.get_header("Accept-language")
        return _Resp()

    monkeypatch.setattr(obs_mod.urllib.request, "urlopen", fake_urlopen)
    assert obs_mod.default_http_get("https://www.evetech.co.za/x") == (200, "ok")
    assert seen["ua"] == LISTING_CAPTURE_USER_AGENT
    assert seen["lang"]
