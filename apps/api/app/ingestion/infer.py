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
    if lower.endswith(".xls"):
        return pd.read_excel(bio, engine="xlrd")
    raise ValueError("Unsupported file type; use .csv, .xlsx, or .xls")


def infer_schema(df: pd.DataFrame) -> dict[str, Any]:
    columns = []
    # Use original column keys for Series lookup — Excel/xlrd can yield int/float
    # headers (e.g. Makro Dispo column ``0``). ``df.columns.astype(str)`` then
    # ``df[str_name]`` raises KeyError when the frame still keys on the numeric label.
    for col in df.columns:
        name = str(col)
        series = df[col]
        dtype = str(series.dtype)
        raw_sample = series.dropna().head(5).tolist()
        sample = [to_jsonable(x) for x in raw_sample]
        columns.append({"name": name, "dtype": dtype, "sample": sample})
    return {"row_count": int(len(df)), "columns": columns}
