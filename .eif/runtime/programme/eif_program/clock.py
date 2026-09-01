"""Clock injection for lease tests."""
from datetime import datetime, timezone

_NOW = None

def now():
    if _NOW is not None:
        return _NOW
    return datetime.now(timezone.utc).replace(microsecond=0)

def iso(dt=None) -> str:
    d = dt or now()
    return d.strftime('%Y-%m-%dT%H:%M:%SZ')

def parse_iso(s: str) -> datetime:
    return datetime.strptime(s, '%Y-%m-%dT%H:%M:%SZ').replace(tzinfo=timezone.utc)

def set_now(dt):
    global _NOW
    _NOW = dt

def reset_now():
    global _NOW
    _NOW = None


set_now = set_now
reset_now = reset_now
