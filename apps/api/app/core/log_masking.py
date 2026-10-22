"""Mask secrets in log lines before they leave the server (N-0089 live log view).

Two layers, both applied to every line:

* exact values: the value of every environment variable (and ``apps/api/.env`` entry) whose name says it
  is a secret, plus the password inside any connection string among them (``PG_OWNER`` included);
* shapes: credentials in connection strings, ``password=...`` / ``"token": "..."`` pairs, bearer and basic
  authorization values, and well-known API key formats.

A line that still carries a secret in a form neither layer knows is the one thing this cannot catch; the
view is admin-only for that reason as well.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from urllib.parse import quote, unquote, urlsplit

MASK = "***"
MAX_LINE_CHARS = 4000

# An environment variable with one of these in its name holds a secret.
_SECRET_NAME_RE = re.compile(
    r"(PASSWORD|PASSWD|PWD|SECRET|TOKEN|API_?KEY|ACCESS_?KEY|PRIVATE|CREDENTIAL|PG_OWNER|DATABASE_URL|"
    r"CONNECTION|DSN|CELERY_BROKER_URL|CELERY_RESULT_BACKEND|SMTP|IMAP)",
    re.IGNORECASE,
)
# Values that are settings, not secrets, even under a secret-looking name.
_NOT_SECRET_VALUES = frozenset(
    {"true", "false", "yes", "no", "on", "off", "none", "null", "session", "1", "0", "localhost"}
)
_MIN_SECRET_LEN = 4

_URL_CREDENTIALS_RE = re.compile(r"(?P<scheme>[A-Za-z][A-Za-z0-9+.\-]*://)(?P<user>[^\s:/@]*):(?P<pw>[^\s@/]+)@")
# key=value, key: value, "key": "value" where the key names a secret.
_KEY_VALUE_RE = re.compile(
    r"""(?ix)
    (?P<key>[\w.\-]*(?:pass(?:word|wd|phrase)|pwd|secret|token(?!s)|api[_\-]?key|apikey|access[_\-]?key|
        private[_\-]?key|credential|pg_owner)[\w.\-]*)
    (?P<sep>["']?\s*[:=]\s*)
    (?:"[^"]*"|'[^']*'|[^\s,;&}\])]+)
    """
)
_AUTH_HEADER_RE = re.compile(
    r"""(?ix)\b(?P<key>proxy-authorization|authorization)(?P<sep>["']?\s*[:=]\s*)
        (?:(?:bearer|basic|token)\s+)?(?:"[^"]*"|'[^']*'|[^\s,;]+)"""
)
_BEARER_RE = re.compile(r"(?i)\b(?P<kind>bearer|basic)\s+[A-Za-z0-9._~+/=\-]{8,}")
_KEY_SHAPES: tuple[re.Pattern[str], ...] = (
    re.compile(r"\bsk-(?:ant-|proj-)?[A-Za-z0-9_\-]{16,}"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"\bgh[pousr]_[A-Za-z0-9]{30,}"),
    re.compile(r"\bxox[abprs]-[A-Za-z0-9\-]{10,}"),
    re.compile(r"\bAIza[0-9A-Za-z_\-]{35}\b"),
    re.compile(r"\beyJ[A-Za-z0-9_\-]{8,}\.[A-Za-z0-9_\-]{8,}\.[A-Za-z0-9_\-]*"),
)


def _api_env_file() -> Path:
    return Path(__file__).resolve().parents[2] / ".env"


def _dotenv_pairs(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return out
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        value = value.strip()
        if value[:1] in ("'", '"') and value[-1:] == value[:1] and len(value) >= 2:
            value = value[1:-1]
        elif " #" in value:
            value = value.split(" #", 1)[0].strip()
        out[key.strip()] = value
    return out


def _values_from(value: str) -> set[str]:
    """The secret value itself and, for a connection string, the password and user:password inside it."""
    found: set[str] = set()
    v = value.strip()
    if len(v) >= _MIN_SECRET_LEN and v.lower() not in _NOT_SECRET_VALUES:
        found.add(v)
    if "://" in v:
        try:
            parts = urlsplit(v)
        except ValueError:
            parts = None
        if parts is not None and parts.password:
            for pw in {parts.password, unquote(parts.password)}:
                if len(pw) >= 1:
                    found.add(pw)
    for item in list(found):
        quoted = quote(item, safe="")
        if quoted != item:
            found.add(quoted)
    return found


def collect_secret_values(environ: dict[str, str] | None = None, env_file: Path | None = None) -> list[str]:
    """Every exact value to mask, longest first so a connection string goes before the password inside it."""
    pairs: dict[str, str] = {}
    pairs.update(_dotenv_pairs(env_file if env_file is not None else _api_env_file()))
    pairs.update(dict(os.environ if environ is None else environ))
    values: set[str] = set()
    for name, value in pairs.items():
        if value and _SECRET_NAME_RE.search(name):
            values |= _values_from(value)
    return sorted(values, key=len, reverse=True)


class LogMasker:
    """Mask secrets in a line. Build one per stream: it reads the environment once."""

    def __init__(self, secret_values: list[str] | None = None) -> None:
        self._values = collect_secret_values() if secret_values is None else sorted(
            {v for v in secret_values if v}, key=len, reverse=True
        )

    def mask(self, line: str) -> str:
        out = line
        for value in self._values:
            if value in out:
                out = out.replace(value, MASK)
        out = _URL_CREDENTIALS_RE.sub(lambda m: f"{m.group('scheme')}{m.group('user')}:{MASK}@", out)
        out = _AUTH_HEADER_RE.sub(lambda m: f"{m.group('key')}{m.group('sep')}{MASK}", out)
        out = _BEARER_RE.sub(lambda m: f"{m.group('kind')} {MASK}", out)
        out = _KEY_VALUE_RE.sub(lambda m: f"{m.group('key')}{m.group('sep')}{MASK}", out)
        for shape in _KEY_SHAPES:
            out = shape.sub(MASK, out)
        if len(out) > MAX_LINE_CHARS:
            out = out[:MAX_LINE_CHARS] + " …[line cut]"
        return out
