"""GS1 modulo-10 helpers for GTIN-8, GTIN-12, GTIN-13 and GTIN-14.

Identifiers must be strings: a numeric value may already have lost leading zeros.
Normalisation removes presentation whitespace/hyphens and returns a validated,
zero-padded GTIN-14. It never repairs a check digit or truncates an identifier.
"""

from __future__ import annotations

_LENGTHS = frozenset({8, 12, 13, 14})


def calculate_check_digit(body: str) -> str:
    """Return the GS1 check digit for a 7, 11, 12 or 13 digit payload.

    Raise ValueError for anything other than ASCII digits of a supported length.
    """
    if (
        not isinstance(body, str)
        or len(body) + 1 not in _LENGTHS
        or not body.isascii()
        or not body.isdigit()
    ):
        raise ValueError("Expected 7, 11, 12 or 13 ASCII digits")
    total = sum(
        int(char) * (3 if index % 2 == 0 else 1) for index, char in enumerate(reversed(body))
    )
    return str((-total) % 10)


def normalize_gtin(raw: object) -> str | None:
    """Return a valid identifier as GTIN-14, or None; all-zero placeholders are refused."""
    if not isinstance(raw, str):
        return None
    compact = "".join(char for char in raw if not char.isspace() and char != "-")
    if (
        len(compact) not in _LENGTHS
        or not compact.isascii()
        or not compact.isdigit()
        or not compact.strip("0")
    ):
        return None
    if calculate_check_digit(compact[:-1]) != compact[-1]:
        return None
    return compact.zfill(14)


def is_valid_gtin(raw: object) -> bool:
    """Whether the supplied complete identifier has a valid GS1 check digit."""
    return normalize_gtin(raw) is not None
