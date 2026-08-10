"""Schema inference must emit JSON-serializable payloads for PostgreSQL JSONB."""

import json

import numpy as np
import pandas as pd

from app.ingestion.infer import infer_schema


def test_infer_schema_json_serializable_with_timestamps() -> None:
    df = pd.DataFrame(
        {
            "sku": ["a"],
            "ship_date": [pd.Timestamp("2024-06-01 12:00:00")],
            "x": [np.int64(42)],
        }
    )
    schema = infer_schema(df)
    json.dumps(schema)
    assert schema["columns"][1]["sample"] == ["2024-06-01T12:00:00"]
    assert schema["columns"][2]["sample"] == [42]


def test_infer_schema_handles_nan_float_sample() -> None:
    df = pd.DataFrame({"v": [float("nan")]})
    schema = infer_schema(df)
    json.dumps(schema)
    assert schema["columns"][0]["sample"] == []


def test_infer_schema_numeric_column_headers() -> None:
    """Excel/xlrd can emit int headers (Makro Dispo ``0`` next to Article)."""
    df = pd.DataFrame([["850008372", "00", "desc"]], columns=["Article", 0, "Article Desc"])
    schema = infer_schema(df)
    json.dumps(schema)
    names = [c["name"] for c in schema["columns"]]
    assert names == ["Article", "0", "Article Desc"]
    assert schema["columns"][1]["sample"] == ["00"]
