"""JSON-safe normalization for PostgreSQL JSONB."""

import json
from datetime import date, datetime
from decimal import Decimal

import numpy as np
import pandas as pd
import pytest

from app.utils.json_safe import to_jsonable


def test_to_jsonable_datetime_and_timestamp() -> None:
    dt = datetime(2024, 3, 1, 8, 0, 0)
    assert to_jsonable(dt) == "2024-03-01T08:00:00"
    ts = pd.Timestamp("2024-03-01 09:00:00")
    assert to_jsonable(ts).startswith("2024-03-01")
    assert to_jsonable(pd.NaT) is None


def test_to_jsonable_numpy_and_nan() -> None:
    assert to_jsonable(np.int64(7)) == 7
    assert to_jsonable(np.float64(float("nan"))) is None
    assert to_jsonable(Decimal("3.14")) == pytest.approx(3.14)


def test_to_jsonable_nested_serializes_with_json_dumps() -> None:
    payload = {
        "row": {
            "d": datetime(2024, 1, 1),
            "x": np.float32(1.5),
            "n": float("nan"),
        }
    }
    out = to_jsonable(payload)
    json.dumps(out)
    assert out["row"]["d"] == "2024-01-01T00:00:00"
    assert out["row"]["n"] is None


def test_to_jsonable_date_only() -> None:
    assert to_jsonable(date(2025, 12, 31)) == "2025-12-31"

