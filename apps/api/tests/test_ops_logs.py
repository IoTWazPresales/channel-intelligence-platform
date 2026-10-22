"""N-0089: the admin live log view. Masking, line parsing, tailing, job-id tagging and the SSE endpoint.

Everything runs on temporary log files (``CIP_LOG_DIR``); no real log or database is read. Secret-shaped
test values are made up here and built at run time, so no key-like literal sits in the file.
"""

from __future__ import annotations

import json
import logging
import threading
import time
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.api.v1.endpoints import ops_logs as ops_logs_endpoint
from app.core.job_log_context import job_log_scope
from app.core.log_masking import MASK, LogMasker, collect_secret_values
from app.core.logging_setup import APP_LOG_FORMAT, configure_api_app_logging
from app.main import app
from app.services import ops_logs
from app.worker import job_log_signals

ADMIN = {"X-User-Role": "admin", "X-User-Id": "test"}

# Made-up values; the shapes are real, the characters are not.
FAKE_PW = "hunter" + "2pw"
FAKE_API_KEY = "sk-" + "ant-api03-" + "Z" * 22
FAKE_JWT = ".".join(["eyJ" + "h" * 12, "eyJ" + "p" * 12, "s" * 12])


# ---------------------------------------------------------------------------------------------- masking

def test_masks_connection_string_credentials_and_key_value_pairs() -> None:
    m = LogMasker([])
    assert m.mask(f"connect postgresql://cip:{FAKE_PW}@localhost:5432/cip failed") == (
        f"connect postgresql://cip:{MASK}@localhost:5432/cip failed"
    )
    assert m.mask(f"retry password={FAKE_PW} host=db") == f"retry password={MASK} host=db"
    assert m.mask('payload {"api_key": "abc123xyz", "n": 5}') == f'payload {{"api_key": {MASK}, "n": 5}}'
    assert m.mask("Authorization: Bearer abcdef0123456789") == f"Authorization: {MASK}"
    assert m.mask("sent with Bearer abcdef0123456789xyz now") == f"sent with Bearer {MASK} now"
    assert m.mask(f"key {FAKE_API_KEY} end") == f"key {MASK} end"
    assert m.mask(f"jwt {FAKE_JWT} end") == f"jwt {MASK} end"


def test_leaves_ordinary_numbers_and_words_alone() -> None:
    m = LogMasker([])
    for line in (
        "rows passed=12 failed=0",
        "tokens_used=500 model=x",
        "imports.cst_apply finished state=SUCCESS in 4.2s",
        "customer sell-through supersede failed job_id=1688: boom",
    ):
        assert m.mask(line) == line


def test_masks_the_values_of_secret_named_environment_variables() -> None:
    owner = "owner-" + "Q7x!made-up"
    mailbox = "made" + "up" + "mailbox" + "pw"
    plain = "plain-" + "made-up-value-123"
    url_pw = "p@ss%20" + "word9"
    env = {
        "PG_OWNER": owner,
        "DATABASE_URL": f"postgresql+asyncpg://cip:{url_pw}@localhost:5432/cip",
        "CIP_MAILBOX_IMAP_PASSWORD": mailbox,
        "SOME_SERVICE_API_KEY": plain,
        "CIP_AUTH_MODE": "session",  # a setting, not a secret
        "PATH": "C:\\Windows",
    }
    values = collect_secret_values(env, env_file=Path("does-not-exist.env"))
    masker = LogMasker(values)
    decoded = url_pw.replace("%20", " ")
    out = masker.mask(f"{owner} and {mailbox} and {plain} and {url_pw} and {decoded} mode=session")
    for secret in (owner, mailbox, plain, url_pw, decoded):
        assert secret not in out
    assert "mode=session" in out
    assert "C:\\Windows" not in values


def test_reads_secret_values_from_the_env_file(tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        "# c\nPG_OWNER='file-owner-value'\nCIP_AUTH_MODE=session\nSOME_TOKEN=abcd1234 # note\n", encoding="utf-8"
    )
    values = collect_secret_values({}, env_file=env_file)
    assert "file-owner-value" in values and "abcd1234" in values and "session" not in values


def test_cuts_a_very_long_line() -> None:
    out = LogMasker([]).mask("x" * 9000)
    assert len(out) < 4100 and out.endswith("…[line cut]")


# ---------------------------------------------------------------------------------------------- parsing

def _parser(source: str = "worker", file: str = "worker.err.log") -> ops_logs.LineParser:
    return ops_logs.LineParser(source, file)


def test_parses_celery_app_lines() -> None:
    ln = _parser().parse("[2026-10-22 21:51:22,858: WARN/MainProcess] [job_id=1688] imports.cst_apply started")
    assert (ln.ts, ln.ts_exact, ln.level, ln.logger, ln.job_id) == (
        "2026-10-22T21:51:22.858", True, "WARNING", "MainProcess", 1688)
    assert ln.text == "[job_id=1688] imports.cst_apply started"


def test_parses_uvicorn_lines_without_a_time() -> None:
    ln = _parser("api", "api.log").parse('INFO:     127.0.0.1:51091 - "GET /api/v1/auth/me HTTP/1.1" 401 Unauthorized')
    assert (ln.ts, ln.ts_exact, ln.level, ln.logger) == (None, False, "INFO", "uvicorn.access")


def test_traceback_lines_follow_the_error_and_its_job() -> None:
    p = _parser("worker", "worker.err.log")
    head = p.parse("[2026-10-22 21:51:22,858: ERROR/MainProcess] cst_apply_task failed job_id=1688 — recording failure")
    tb = p.parse("Traceback (most recent call last):")
    frame = p.parse('  File "x.py", line 3, in apply')
    last = p.parse("ValueError: boom")
    assert head.level == "ERROR" and not head.cont
    for ln in (tb, frame, last):
        assert (ln.level, ln.cont, ln.job_id, ln.ts) == ("ERROR", True, 1688, head.ts)
    assert p.parse("some later bare text").cont is False


def test_unrecognised_api_lines_are_warnings_but_other_sources_info() -> None:
    assert _parser("api", "api.err.log").parse("report schedule poll reason=interval {}").level == "WARNING"
    assert _parser("web", "web.log").parse("ready - started server").level == "INFO"


def test_supervisor_lines_get_a_level_from_their_words() -> None:
    p = _parser("supervisor", "supervisor.log")
    assert p.parse("2026-10-22T21:51:22 api: starting -> healthy pid 5").level == "INFO"
    assert p.parse("2026-10-22T21:51:22 worker: healthy -> dead wrapper exited").level == "WARNING"
    assert p.parse("2026-10-22T21:51:22 tunnel: CLOSING the public tunnel - x").level == "ERROR"


# ---------------------------------------------------------------------------------------------- tailing

def _write(path: Path, *lines: str, mode: str = "a") -> None:
    with open(path, mode, encoding="utf-8", newline="\n") as fh:
        for line in lines:
            fh.write(line + "\n")


def _celery(ts: str, level: str, msg: str) -> str:
    return f"[2026-10-22 {ts}: {level}/MainProcess] {msg}"


def test_backlog_then_poll_returns_only_new_lines_and_masks(tmp_path: Path) -> None:
    f = tmp_path / "worker.err.log"
    _write(f, _celery("10:00:00,100", "INFO", "first"), _celery("10:00:01,000", "INFO", f"password={FAKE_PW}"))
    s = ops_logs.LogStream(["worker"], masker=LogMasker([]), directory=tmp_path)
    back = s.backlog(300)
    assert [d["text"] for d in back] == ["first", f"password={MASK}"]
    assert [d["id"] for d in back] == [1, 2]
    assert s.poll() == []
    _write(f, _celery("10:00:05,000", "ERROR", "boom job_id=9"))
    new = s.poll()
    assert [(d["level"], d["text"], d["job_id"], d["id"]) for d in new] == [("ERROR", "boom job_id=9", 9, 3)]
    assert s.poll() == []


def test_a_line_still_being_written_waits_for_its_newline(tmp_path: Path) -> None:
    f = tmp_path / "worker.err.log"
    _write(f, _celery("10:00:00,100", "INFO", "one"))
    s = ops_logs.LogStream(["worker"], masker=LogMasker([]), directory=tmp_path)
    s.backlog(10)
    with open(f, "a", encoding="utf-8", newline="\n") as fh:
        fh.write(_celery("10:00:01,000", "INFO", "half a li"))
    assert s.poll() == []
    with open(f, "a", encoding="utf-8", newline="\n") as fh:
        fh.write("ne\n")
    assert [d["text"] for d in s.poll()] == ["half a line"]


def test_a_rotated_file_is_read_again_from_its_start(tmp_path: Path) -> None:
    f = tmp_path / "worker.err.log"
    _write(f, _celery("10:00:00,100", "INFO", "old one"), _celery("10:00:00,200", "INFO", "old two"))
    s = ops_logs.LogStream(["worker"], masker=LogMasker([]), directory=tmp_path)
    s.backlog(10)
    _write(f, _celery("11:00:00,000", "INFO", "new"), mode="w")  # shorter than before: replaced
    assert [d["text"] for d in s.poll()] == ["new"]


def test_levels_and_health_checks_are_filtered(tmp_path: Path) -> None:
    _write(
        tmp_path / "api.log",
        'INFO:     127.0.0.1:1 - "GET /health HTTP/1.1" 200 OK',
        'INFO:     127.0.0.1:1 - "GET /api/v1/x HTTP/1.1" 200 OK',
    )
    _write(tmp_path / "worker.err.log", _celery("10:00:00,100", "INFO", "info"), _celery("10:00:01,000", "ERROR", "bad"))
    default = ops_logs.LogStream(["api", "worker"], masker=LogMasker([]), directory=tmp_path).backlog(50)
    assert [d["text"] for d in default if d["source"] == "api"] == []  # web requests are opt-in
    everything = ops_logs.LogStream(
        ["api", "worker"], include_access=True, masker=LogMasker([]), directory=tmp_path
    ).backlog(50)
    assert [d["text"] for d in everything if d["source"] == "api"] == ['127.0.0.1:1 - "GET /api/v1/x HTTP/1.1" 200 OK']
    errors = ops_logs.LogStream(
        ["api", "worker"], min_level="error", masker=LogMasker([]), directory=tmp_path
    ).backlog(50)
    assert [d["text"] for d in errors] == ["bad"]


def test_job_filter_keeps_that_jobs_lines_and_its_traceback_and_reads_the_previous_generation(tmp_path: Path) -> None:
    _write(tmp_path / "worker.err.log.1", _celery("09:00:00,000", "INFO", "[job_id=5] imports.cst_apply started"))
    _write(
        tmp_path / "worker.err.log",
        _celery("10:00:00,000", "INFO", "[job_id=6] other job"),
        _celery("10:00:01,000", "ERROR", "[job_id=5] cst_apply_task failed"),
        "Traceback (most recent call last):",
        "ValueError: boom",
        _celery("10:00:02,000", "INFO", "no job named here"),
    )
    got = ops_logs.LogStream(["worker"], job_id=5, masker=LogMasker([]), directory=tmp_path).backlog(50)
    assert [d["text"] for d in got] == [
        "[job_id=5] imports.cst_apply started",
        "[job_id=5] cst_apply_task failed",
        "Traceback (most recent call last):",
        "ValueError: boom",
    ]
    assert [d["ts"] for d in got][:2] == ["2026-10-22T09:00:00.000", "2026-10-22T10:00:01.000"]


def test_backlog_merges_sources_by_time_and_caps_the_count(tmp_path: Path) -> None:
    _write(tmp_path / "worker.err.log", _celery("10:00:00,000", "INFO", "w1"), _celery("10:00:02,000", "INFO", "w2"))
    _write(tmp_path / "supervisor.log", "2026-10-22T10:00:01 s1", "2026-10-22T10:00:03 s2")
    s = ops_logs.LogStream(["worker", "supervisor"], masker=LogMasker([]), directory=tmp_path)
    assert [d["text"] for d in s.backlog(300)] == ["w1", "s1", "w2", "s2"]
    s2 = ops_logs.LogStream(["worker", "supervisor"], masker=LogMasker([]), directory=tmp_path)
    assert [d["text"] for d in s2.backlog(2)] == ["w2", "s2"]


def test_missing_files_are_empty_not_an_error(tmp_path: Path) -> None:
    s = ops_logs.LogStream(None, masker=LogMasker([]), directory=tmp_path / "nope")
    assert s.backlog(10) == [] and s.poll() == []


def test_latest_errors_counts_a_traceback_once(tmp_path: Path) -> None:
    _write(
        tmp_path / "worker.err.log",
        _celery("10:00:00,000", "ERROR", "first failed"),
        "Traceback (most recent call last):",
        "ValueError: boom",
        _celery("10:05:00,000", "ERROR", f"second failed password={FAKE_PW}"),
        _celery("10:06:00,000", "INFO", "fine"),
    )
    all_errors = ops_logs.latest_errors(None, masker=LogMasker([]), directory=tmp_path)
    assert all_errors["count_since"] == 2
    assert all_errors["latest"]["text"] == f"second failed password={MASK}"
    since = ops_logs.latest_errors("2026-10-22T10:00:00.000", masker=LogMasker([]), directory=tmp_path)
    assert since["count_since"] == 1 and since["latest_ts"] == "2026-10-22T10:05:00.000"
    assert ops_logs.latest_errors("2026-10-22T10:05:00.000", masker=LogMasker([]), directory=tmp_path)["count_since"] == 0


# ---------------------------------------------------------------------------------------------- job tagging

def test_log_lines_inside_a_job_scope_carry_the_job_id(caplog: pytest.LogCaptureFixture) -> None:
    log = logging.getLogger("app.test_job_tagging")
    with caplog.at_level(logging.INFO, logger="app.test_job_tagging"):
        with job_log_scope(42):
            log.info("validating %s rows", 7)
            log.warning("already names job_id=%s", 42)
        log.info("outside the scope")
    assert [r.getMessage() for r in caplog.records] == [
        "[job_id=42] validating 7 rows",
        "already names job_id=42",
        "outside the scope",
    ]


def test_import_job_id_comes_from_the_first_argument_of_imports_tasks_only() -> None:
    f = job_log_signals.import_job_id_from_task
    assert f("imports.cst_apply", (1688,), {}) == 1688
    assert f("imports.dsi_apply", (), {"job_id": 9}) == 9
    assert f("imports.reap_stale_running_jobs", (), {}) is None
    assert f("imports.cst_bulk_ignore", ({"x": 1},), {}) is None
    assert f("reports.run_due_schedules", (5,), {}) is None
    assert f("imports.cst_apply", (True,), {}) is None


def test_task_signals_write_a_start_and_a_finish_line_for_the_job(caplog: pytest.LogCaptureFixture) -> None:
    task = SimpleNamespace(name="imports.cst_apply")
    inner = logging.getLogger("app.services.imports.cst_apply_sync")
    with caplog.at_level(logging.INFO, logger="app"):
        job_log_signals._job_log_start(task_id="t-1", task=task, args=(1688,), kwargs={})
        inner.warning("in between")
        job_log_signals._job_log_finish(task_id="t-1", task=task, state="SUCCESS")
        inner.warning("after")
    messages = [r.getMessage() for r in caplog.records]
    assert messages[0].startswith("[job_id=1688] imports.cst_apply started (task t-1)")
    assert messages[1] == "[job_id=1688] in between"
    assert messages[2].startswith("[job_id=1688] imports.cst_apply finished state=SUCCESS in ")
    assert messages[3] == "after"
    assert "t-1" not in job_log_signals._open


def test_api_app_logger_gets_a_timestamp_and_level() -> None:
    app_logger = logging.getLogger("app")
    before_handlers, before_level = list(app_logger.handlers), app_logger.level
    try:
        assert configure_api_app_logging(force=True) is True
        assert configure_api_app_logging(force=True) is False  # once
        handler = next(h for h in app_logger.handlers if h not in before_handlers)
        rec = logging.LogRecord("app.x", logging.INFO, __file__, 1, "hello %s", ("there",), None)
        assert handler.format(rec).endswith(": INFO/app.x] hello there")
        assert handler.formatter._fmt == APP_LOG_FORMAT
    finally:
        app_logger.handlers = before_handlers
        app_logger.setLevel(before_level)


# ---------------------------------------------------------------------------------------------- endpoint

@pytest.mark.parametrize("path", ["/api/v1/admin/logs/stream", "/api/v1/admin/logs/errors"])
def test_log_endpoints_are_admin_only(path: str) -> None:
    with TestClient(app) as client:
        for role in ("planner", "steward"):
            r = client.get(path, headers={"X-User-Role": role, "X-User-Id": "probe"})
            assert r.status_code == 403


def _sse(text: str) -> list[tuple[str, dict]]:
    events: list[tuple[str, dict]] = []
    for block in text.split("\n\n"):
        name, data = None, None
        for line in block.splitlines():
            if line.startswith("event: "):
                name = line[7:]
            elif line.startswith("data: "):
                data = json.loads(line[6:])
        if name and data is not None:
            events.append((name, data))
    return events


def test_stream_sends_the_backlog_then_new_lines_masked(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CIP_LOG_DIR", str(tmp_path))
    monkeypatch.setattr(ops_logs_endpoint, "POLL_SECONDS", 0.05)
    monkeypatch.setattr(ops_logs_endpoint, "MAX_STREAM_SECONDS", 1.5)
    f = tmp_path / "worker.err.log"
    _write(
        f,
        _celery("10:00:00,000", "INFO", "[job_id=5] imports.cst_apply started"),
        _celery("10:00:01,000", "INFO", "[job_id=6] someone else"),
    )

    def append_later() -> None:
        time.sleep(0.5)
        _write(f, _celery("10:00:09,000", "ERROR", f"[job_id=5] failed password={FAKE_PW}"))

    t = threading.Thread(target=append_later)
    t.start()
    with TestClient(app) as client:
        with client.stream("GET", "/api/v1/admin/logs/stream?sources=worker&job_id=5", headers=ADMIN) as r:
            assert r.status_code == 200
            assert r.headers["content-type"].startswith("text/event-stream")
            assert "no-transform" in r.headers["cache-control"]
            body = "".join(r.iter_text())
    t.join()
    events = _sse(body)
    names = [n for n, _ in events]
    assert names[0] == "backlog" and names[-1] == "end"
    assert [ln["text"] for ln in events[0][1]["lines"]] == ["[job_id=5] imports.cst_apply started"]
    streamed = [ln for n, d in events if n == "lines" for ln in d["lines"]]
    assert [(ln["level"], ln["text"]) for ln in streamed] == [("ERROR", f"[job_id=5] failed password={MASK}")]
    assert FAKE_PW not in body


def test_errors_endpoint_returns_the_newest_error(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CIP_LOG_DIR", str(tmp_path))
    _write(tmp_path / "worker.err.log", _celery("10:00:00,000", "ERROR", "bad thing"))
    with TestClient(app) as client:
        r = client.get("/api/v1/admin/logs/errors", headers=ADMIN)
        assert r.status_code == 200
        body = r.json()
        assert body["count_since"] == 1 and body["latest"]["text"] == "bad thing"
        r2 = client.get("/api/v1/admin/logs/errors?since=2026-10-22T10:00:00.000", headers=ADMIN)
        assert r2.json()["count_since"] == 0
