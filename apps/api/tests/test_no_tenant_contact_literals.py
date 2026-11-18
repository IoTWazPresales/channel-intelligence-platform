"""Application code holds no person addresses or workstation paths (alignment D9).

Recipients, senders and file locations are tenant configuration, not code. Example
domains reserved for documentation (RFC 2606) are allowed.
"""

from __future__ import annotations

import re
from pathlib import Path

APP = Path(__file__).resolve().parents[1] / "app"
_EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@([A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+)")
_ALLOWED_DOMAINS = ("example.com", "example.org", "example.net", "example.test", "localhost")
_WORKSTATION = re.compile(r"[A-Za-z]:\\{1,2}Users\\{1,2}|OneDrive - ", re.IGNORECASE)


def _sources():
    for path in sorted(APP.rglob("*.py")):
        yield path, path.read_text(encoding="utf-8", errors="replace")


def test_no_person_email_literals_in_app_code() -> None:
    hits = []
    for path, text in _sources():
        for match in _EMAIL.finditer(text):
            domain = match.group(1).lower()
            if domain.endswith(_ALLOWED_DOMAINS):
                continue
            hits.append(f"{path.relative_to(APP)}: {match.group(0)}")
    assert hits == []


def test_no_workstation_paths_in_app_code() -> None:
    hits = [str(path.relative_to(APP)) for path, text in _sources() if _WORKSTATION.search(text)]
    assert hits == []
