"""``browser_available`` must require an installed chromium binary."""

from __future__ import annotations

from app.services.listing_capture.web_discovery import crawl


def test_browser_available_false_when_chromium_missing(monkeypatch, tmp_path) -> None:
    missing = tmp_path / "no-chromium"
    monkeypatch.setattr(crawl, "crawlee_available", lambda: True)
    monkeypatch.setattr(crawl, "_chromium_executable_path", lambda: str(missing))
    assert crawl.browser_available() is False


def test_browser_available_true_when_chromium_present(tmp_path, monkeypatch) -> None:
    exe = tmp_path / "chrome"
    exe.write_text("", encoding="utf-8")
    monkeypatch.setattr(crawl, "crawlee_available", lambda: True)
    monkeypatch.setattr(crawl, "_chromium_executable_path", lambda: str(exe))
    assert crawl.browser_available() is True