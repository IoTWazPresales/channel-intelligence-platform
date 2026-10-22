"""Read the always-on stack's existing log files for the admin live log view (N-0089).

No new logging stack and no shipping: the supervisor already writes each component's stdout and stderr to
``%LOCALAPPDATA%\\CIP\\always-on\\logs`` (``CIP_LOG_DIR`` overrides it). This module tails those files, turns each line
into ``{source, ts, level, logger, text, job_id}`` and masks secrets before anything is returned.

* The files rotate only when a process launches (``name.log`` -> ``name.log.1`` -> ``name.log.2``), so a poll opens
  and closes each file rather than holding a handle (a held handle makes the supervisor's rename fail), and a file
  that got smaller or was replaced is read again from its start.
* Four line shapes exist: Celery / app (``[2026-10-22 21:51:22,858: INFO/MainProcess] msg``), uvicorn
  (``INFO:     msg``, no time), the supervisor (``2026-10-22T21:51:22 msg``) and bare text (tracebacks, print).
  Times are the machine's local time, as written.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable

from app.core.log_masking import LogMasker

LEVEL_ORDER = {"DEBUG": 10, "INFO": 20, "WARNING": 30, "ERROR": 40, "CRITICAL": 50}
_LEVEL_ALIASES = {"WARN": "WARNING", "FATAL": "CRITICAL", "EXCEPTION": "ERROR", "TRACE": "DEBUG"}

# source -> (file names, level of an unrecognised line). The API's bare stderr lines come from Python's
# last-resort handler, which only ever writes WARNING and above.
SOURCES: dict[str, tuple[tuple[str, ...], str]] = {
    "api": (("api.err.log", "api.log"), "WARNING"),
    "worker": (("worker.err.log", "worker.log"), "INFO"),
    "web": (("web.err.log", "web.log"), "INFO"),
    "supervisor": (("supervisor.log",), "INFO"),
}
DEFAULT_SOURCES = tuple(SOURCES)

BACKLOG_BYTES = 400_000
JOB_BACKLOG_BYTES = 2_000_000
POLL_CHUNK_BYTES = 1_000_000

_CELERY_RE = re.compile(
    r"^\[(?P<ts>\d{4}-\d\d-\d\d \d\d:\d\d:\d\d(?:,\d{1,6})?): (?P<level>[A-Za-z]+)/(?P<logger>[^\]]*)\] ?(?P<msg>.*)$"
)
_UVICORN_RE = re.compile(r"^(?P<level>DEBUG|INFO|WARNING|ERROR|CRITICAL):\s+(?P<msg>.*)$")
_SUPERVISOR_RE = re.compile(r"^(?P<ts>\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d)\s+(?P<msg>.*)$")
_TRACEBACK_START = ("Traceback (most recent call last)", "During handling of the above", "The above exception")
_EXCEPTION_LINE_RE = re.compile(r"^[A-Za-z_][\w.]*(?:Error|Exception|Exit|Interrupt|Timeout)\b")
_JOB_RES = (re.compile(r"\bjob_id=(\d+)"), re.compile(r"\bjob[ #]+(\d{1,9})\b", re.IGNORECASE))
_HEALTH_ACCESS_RE = re.compile(r'"GET /health(?:/\w+)? HTTP/')
_SUPERVISOR_ERROR_RE = re.compile(r"\b(error|exception|traceback|could not|CLOSING)\b", re.IGNORECASE)
_SUPERVISOR_WARN_RE = re.compile(r"\b(dead|flapping|unhealthy|backoff|blocked|held)\b", re.IGNORECASE)


def log_dir() -> Path:
    override = os.environ.get("CIP_LOG_DIR", "").strip()
    if override:
        return Path(override)
    base = os.environ.get("LOCALAPPDATA", "").strip()
    if base:
        return Path(base) / "CIP" / "always-on" / "logs"
    return Path.home() / ".local" / "state" / "cip" / "logs"


def normalise_level(value: str | None) -> str:
    v = (value or "").strip().upper()
    v = _LEVEL_ALIASES.get(v, v)
    return v if v in LEVEL_ORDER else "INFO"


def level_at_least(level: str, minimum: str | None) -> bool:
    return minimum is None or LEVEL_ORDER.get(level, 20) >= LEVEL_ORDER.get(minimum, 0)


def _iso_from_celery(ts: str) -> str:
    date, _, rest = ts.partition(" ")
    clock, _, frac = rest.partition(",")
    return f"{date}T{clock}" + (f".{frac.ljust(3, '0')[:3]}" if frac else "")


def job_id_in(text: str) -> int | None:
    for rx in _JOB_RES:
        m = rx.search(text)
        if m:
            return int(m.group(1))
    return None


@dataclass
class LogLine:
    source: str
    file: str
    ts: str | None
    ts_exact: bool
    level: str
    logger: str
    text: str
    job_id: int | None
    cont: bool = False  # continues the line before it (traceback, wrapped text)


class LineParser:
    """Parses one file's lines in order; continuation lines (tracebacks, wrapped text) inherit from the line before."""

    def __init__(self, source: str, file: str) -> None:
        self.source = source
        self.file = file
        self.default_level = SOURCES[source][1]
        self.last: LogLine | None = None

    def parse(self, raw: str) -> LogLine | None:
        raw = raw.rstrip("\r\n")
        if not raw.strip():
            return None
        ts: str | None = None
        exact = False
        logger_name = ""
        level: str | None = None
        text = raw

        m = _CELERY_RE.match(raw)
        if m:
            ts, exact = _iso_from_celery(m.group("ts")), True
            level, logger_name, text = normalise_level(m.group("level")), m.group("logger"), m.group("msg")
        else:
            m = _UVICORN_RE.match(raw)
            if m:
                level, text = m.group("level"), m.group("msg")
                logger_name = "uvicorn.access" if "HTTP/" in text else "uvicorn"
            elif self.source == "supervisor":
                m = _SUPERVISOR_RE.match(raw)
                if m:
                    ts, exact, text = m.group("ts"), True, m.group("msg")
                    level = (
                        "ERROR" if _SUPERVISOR_ERROR_RE.search(text)
                        else "WARNING" if _SUPERVISOR_WARN_RE.search(text)
                        else "INFO"
                    )
                    logger_name = "supervisor"

        prev = self.last
        cont = False
        if level is None:
            starts_traceback = raw.startswith(_TRACEBACK_START)
            indented = raw[:1] in (" ", "\t")
            exception_line = prev is not None and prev.level == "ERROR" and bool(_EXCEPTION_LINE_RE.match(raw))
            cont = prev is not None and (starts_traceback or indented or exception_line)
            if starts_traceback:
                level = "ERROR"
            elif cont and prev is not None:
                level = prev.level
            else:
                level = self.default_level
            if prev is not None:
                ts, logger_name = prev.ts, prev.logger
            text = raw

        job_id = job_id_in(text)
        if job_id is None and cont and prev is not None:
            job_id = prev.job_id  # a traceback belongs to the job of the line it follows
        line = LogLine(self.source, self.file, ts, exact, level, logger_name, text, job_id, cont)
        self.last = line
        return line


def _decode(chunk: bytes) -> str:
    try:
        return chunk.decode("utf-8")
    except UnicodeDecodeError:
        return chunk.decode("cp1252", errors="replace")


def _read_range(path: Path, start: int, end: int) -> bytes:
    with open(path, "rb") as fh:
        fh.seek(start)
        return fh.read(max(0, end - start))


def _identity(st: os.stat_result) -> tuple:
    return (st.st_ino, getattr(st, "st_birthtime", None))


class FileTail:
    """One file: a backlog read of its end, then complete new lines on each poll."""

    def __init__(self, source: str, path: Path) -> None:
        self.source = source
        self.path = path
        self.parser = LineParser(source, path.name)
        self.offset: int | None = None
        self._identity: tuple | None = None

    def backlog(self, max_bytes: int) -> list[LogLine]:
        try:
            st = self.path.stat()
        except OSError:
            self.offset = 0
            return []
        size = st.st_size
        start = max(0, size - max_bytes)
        data = _read_range(self.path, start, size)
        self._identity = _identity(st)
        # Only whole lines: drop a partial first line, hold back a partial last one for the next poll.
        end = data.rfind(b"\n") + 1
        if start > 0:
            first = data.find(b"\n") + 1
            data = data[first:end] if first <= end else b""
        else:
            data = data[:end]
        self.offset = start + end if end else (0 if start == 0 else size)
        out: list[LogLine] = []
        for raw in _decode(data).splitlines():
            line = self.parser.parse(raw)
            if line is not None:
                out.append(line)
        return out

    def poll(self) -> list[LogLine]:
        if self.offset is None:
            self.backlog(0)
            return []
        try:
            st = self.path.stat()
        except OSError:
            return []
        if st.st_size < self.offset or (self._identity is not None and _identity(st) != self._identity):
            self.offset = 0  # rotated or truncated: read the new file from its start
            self.parser.last = None
        self._identity = _identity(st)
        if st.st_size <= self.offset:
            return []
        end = min(st.st_size, self.offset + POLL_CHUNK_BYTES)
        data = _read_range(self.path, self.offset, end)
        cut = data.rfind(b"\n") + 1
        if cut == 0:
            if len(data) < POLL_CHUNK_BYTES:
                return []  # a line still being written
            cut = len(data)
        self.offset += cut
        out: list[LogLine] = []
        for raw in _decode(data[:cut]).splitlines():
            line = self.parser.parse(raw)
            if line is not None:
                out.append(line)
        return out


def _mtime_iso(path: Path) -> str | None:
    try:
        return datetime.fromtimestamp(path.stat().st_mtime).isoformat(timespec="milliseconds")
    except OSError:
        return None


def _fill_times(lines: list[LogLine], fallback: str | None) -> None:
    """Lines without a time of their own (uvicorn, bare text) take the time of the line before; the file time
    covers a file with none. They keep ``ts_exact=False`` so the view can show the time as approximate."""
    carry: str | None = None
    for ln in lines:
        if ln.ts_exact:
            carry = ln.ts
        elif ln.ts is None:
            ln.ts = carry
    first_exact = next((ln.ts for ln in lines if ln.ts_exact), None)
    for ln in lines:
        if ln.ts is None:
            ln.ts = first_exact or fallback


def _generations(directory: Path, name: str, with_previous: bool) -> list[Path]:
    paths = [directory / name]
    if with_previous:
        paths.insert(0, directory / f"{name}.1")
    return paths


class LogStream:
    """The lines of the chosen sources, filtered and masked: ``backlog()`` once, then ``poll()`` for what is new."""

    def __init__(
        self,
        sources: Iterable[str] | None = None,
        *,
        job_id: int | None = None,
        min_level: str | None = None,
        include_access: bool = False,
        masker: LogMasker | None = None,
        directory: Path | None = None,
    ) -> None:
        chosen = [s for s in (sources or DEFAULT_SOURCES) if s in SOURCES]
        self.sources = chosen or list(DEFAULT_SOURCES)
        self.job_id = job_id
        self.include_access = include_access
        self.min_level = normalise_level(min_level) if min_level else None
        self.masker = masker or LogMasker()
        self.directory = directory or log_dir()
        self._tails: list[FileTail] = []
        for source in self.sources:
            for name in SOURCES[source][0]:
                self._tails.append(FileTail(source, self.directory / name))
        self._next_id = 1

    def _keep(self, ln: LogLine) -> bool:
        if ln.logger == "uvicorn.access":
            # One line per web request fills any buffer, so they are opt-in; the supervisor's own health
            # checks (every few seconds) are never sent.
            if not self.include_access or _HEALTH_ACCESS_RE.search(ln.text):
                return False
        if self.job_id is not None and ln.job_id != self.job_id:
            return False
        return level_at_least(ln.level, self.min_level)

    def _dicts(self, lines: list[LogLine]) -> list[dict]:
        out = []
        for ln in lines:
            if not self._keep(ln):
                continue
            out.append(
                {
                    "id": self._next_id,
                    "source": ln.source,
                    "file": ln.file,
                    "ts": ln.ts,
                    "ts_exact": ln.ts_exact,
                    "level": ln.level,
                    "logger": ln.logger,
                    "text": self.masker.mask(ln.text),
                    "job_id": ln.job_id,
                    "cont": ln.cont,
                }
            )
            self._next_id += 1
        return out

    def backlog(self, max_lines: int = 300) -> list[dict]:
        max_bytes = JOB_BACKLOG_BYTES if self.job_id is not None else BACKLOG_BYTES
        collected: list[LogLine] = []
        for source in self.sources:
            for name in SOURCES[source][0]:
                tail = next(t for t in self._tails if t.source == source and t.path.name == name)
                lines: list[LogLine] = []
                if self.job_id is not None:
                    # The generation before the last launch may hold the job's earlier lines.
                    prev = FileTail(source, self.directory / f"{name}.1")
                    lines.extend(prev.backlog(max_bytes))
                    _fill_times(lines, _mtime_iso(prev.path))
                current = tail.backlog(max_bytes)
                _fill_times(current, _mtime_iso(tail.path))
                collected.extend(lines + current)
        collected.sort(key=lambda ln: ln.ts or "")  # stable: a file's own order holds when times tie
        kept = [ln for ln in collected if self._keep(ln)]
        if max_lines >= 0:
            kept = kept[-max_lines:] if max_lines else []
        return self._dicts(kept)

    def poll(self) -> list[dict]:
        now = datetime.now().isoformat(timespec="milliseconds")
        fresh: list[LogLine] = []
        for tail in self._tails:
            new = tail.poll()
            for ln in new:
                if ln.ts is None:
                    ln.ts = now
            fresh.extend(new)
        fresh.sort(key=lambda ln: ln.ts or "")
        return self._dicts(fresh)


def latest_errors(
    since: str | None,
    *,
    sources: Iterable[str] | None = None,
    masker: LogMasker | None = None,
    directory: Path | None = None,
    tail_bytes: int = 256_000,
) -> dict:
    """ERROR / CRITICAL lines in the current log files: the newest one and how many are newer than ``since``."""
    stream = LogStream(sources, min_level="ERROR", masker=masker, directory=directory)
    lines: list[LogLine] = []
    for tail in stream._tails:
        part = tail.backlog(tail_bytes)
        _fill_times(part, _mtime_iso(tail.path))
        lines.extend(part)
    lines.sort(key=lambda ln: ln.ts or "")
    errors = [ln for ln in lines if stream._keep(ln)]
    # A traceback is one error, not one per line: count only the line that starts it.
    heads = [ln for ln in errors if not ln.cont]
    newer = [ln for ln in heads if since is None or (ln.ts or "") > since]
    latest = stream._dicts(heads[-1:]) if heads else []
    return {
        "latest_ts": latest[0]["ts"] if latest else None,
        "latest": latest[0] if latest else None,
        "count_since": len(newer),
    }
