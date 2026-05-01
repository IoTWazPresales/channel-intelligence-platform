from __future__ import annotations

import io
from typing import Any

import pandas as pd

from app.utils.json_safe import to_jsonable


def read_tabular(filename: str, raw: bytes) -> pd.DataFrame:
    lower = filename.lower()
    bio = io.BytesIO(raw)
    if lower.endswith(".csv"):
        return pd.read_csv(bio)
    if lower.endswith(".xlsx") or lower.endswith(".xlsm"):
        return pd.read_excel(bio, engine="openpyxl")
    raise ValueError("Unsupported file type; use .csv or .xlsx")


def infer_schema(df: pd.DataFrame) -> dict[str, Any]:
    columns = []
    for col in df.columns.astype(str).tolist():
        series = df[col]
        dtype = str(series.dtype)
        raw_sample = series.dropna().head(5).tolist()
        sample = [to_jsonable(x) for x in raw_sample]
        columns.append({"name": col, "dtype": dtype, "sample": sample})
    return {"row_count": int(len(df)), "columns": columns}
