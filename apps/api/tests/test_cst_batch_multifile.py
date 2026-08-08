"""CST multi-file batch (DSI parity) — propose + create + per-file periods."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.services.imports.cst_batch import (
    CST_CAPABLE_GROUP_SIGNATURE,
    propose_cst_batch_groups,
)

PILOT = Path(__file__).resolve().parents[3] / ".tmp" / "cst_pilot_takealot"


@pytest.mark.skipif(not PILOT.exists(), reason="pilot Takealot WEEK files not present")
def test_propose_cst_batch_takealot_weeks_capable():
    files = sorted(PILOT.glob("ASUS WEEK *.xlsx"))
    assert len(files) >= 2
    payload = [(f.name, f.read_bytes()) for f in files[:4]]
    groups = propose_cst_batch_groups(payload)
    capable = [g for g in groups if g.signature == CST_CAPABLE_GROUP_SIGNATURE]
    assert len(capable) == 1
    assert len(capable[0].files) == len(payload)
    assert all(not f.unmappable for f in capable[0].files)


def test_propose_cst_batch_rejects_non_cst_bytes():
    groups = propose_cst_batch_groups([("notes.txt", b"hello world\nnot a workbook")])
    assert groups
    assert all(f.unmappable for g in groups for f in g.files)
