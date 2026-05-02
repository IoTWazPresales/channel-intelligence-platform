"""Convert Python values to JSON-serializable structures for PostgreSQL JSONB (psycopg)."""

from __future__ import annotations

import json
import math
from datetime import date, datetime, time
from decimal import Decimal
from enum import Enum
from typing import Any
from uuid import UUID

import pandas as pd

try:
    import numpy as np
except ImportError:  # pragma: no cover
    np = None  # type: ignore[misc, assignment]


def to_jsonable(value: Any, *, _depth: int = 0) -> Any:
    """Recursively normalize values for JSON/JSONB persistence.

    Handles datetime/date/time, pandas Timestamp/NaT/Timedelta, numpy scalars and arrays,
    NaN/NaT/None, dict/list/tuple/set, Decimal, UUID, Enum, bytes, and falls back to ``str``.
    """
    if _depth > 48:
        return str(value)

    if value is None:
        return None

    try:
        from pandas.api.types import is_scalar as pd_is_scalar

        if pd_is_scalar(value) and pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass

    if isinstance(value, bool):
        return value

    if isinstance(value, (int, float)):
        if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
            return None
        return value

    if isinstance(value, str):
        return value

    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")

    if isinstance(value, UUID):
        return str(value)

    if isinstance(value, Decimal):
        if value.is_nan():
            return None
        return float(value)

    if isinstance(value, Enum):
        return to_jsonable(value.value, _depth=_depth + 1)

    # pd.Timestamp subclasses datetime; handle NaT before isoformat()
    if isinstance(value, pd.Timestamp):
        if pd.isna(value):
            return None
        return value.isoformat()

    if isinstance(value, (datetime, date, time)):
        return value.isoformat()

    if isinstance(value, pd.Timedelta):
        return str(value)

    if np is not None:
        if isinstance(value, np.ndarray):
            return [to_jsonable(x, _depth=_depth + 1) for x in value.tolist()]
        if isinstance(value, np.generic):
            try:
                return to_jsonable(value.item(), _depth=_depth + 1)
            except (ValueError, AttributeError):
                return str(value)

    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for k, v in value.items():
            out[str(k)] = to_jsonable(v, _depth=_depth + 1)
        return out

    if isinstance(value, (list, tuple)):
        return [to_jsonable(x, _depth=_depth + 1) for x in value]

    if isinstance(value, (set, frozenset)):
        return [to_jsonable(x, _depth=_depth + 1) for x in value]

    if hasattr(value, "isoformat") and callable(value.isoformat):
        try:
            return value.isoformat()
        except (TypeError, ValueError):
            pass

    if hasattr(value, "item"):
        try:
            return to_jsonable(value.item(), _depth=_depth + 1)
        except (ValueError, AttributeError, TypeError):
            return str(value)

    return str(value)


def verify_json_serializable(label: str, payload: Any) -> None:
    """Ensure ``payload`` is safe for PostgreSQL JSONB after ``to_jsonable`` (DSI staging / audit).

    Raises ``ValueError`` with a user-safe message if serialization still fails.
    """
    try:
        json.dumps(to_jsonable(payload), allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise ValueError(
            "Uploaded row contains a value that could not be converted for audit storage "
            f"({label}): {exc}"
        ) from exc
