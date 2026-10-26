"""Probe scoped portfolio supplemental omission, with no database connections."""
import json
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "apps/api"))
from sqlalchemy import event
from sqlalchemy.engine import Engine

@event.listens_for(Engine, "do_connect")
def no_database(*args, **kwargs):
    raise AssertionError("Database access forbidden for this pure probe")

from app.services.cpor.portfolio_intelligence import build_portfolio_intelligence

def session():
    s = MagicMock()
    line = SimpleNamespace(product_id=1, estimate_qty=10, result_qty=5, ttl_support_usd=20, ttl_support=360, support_usd=None, remark=None)
    case = SimpleNamespace(id=1, customer_id=7, promotion_type="fictional", lines=[line])
    s.scalars.return_value.unique.return_value.all.return_value = [case]
    s.execute.side_effect = [MagicMock(all=lambda: [(7, "fictional", "Fictional")]), MagicMock(all=lambda: [(1, "NB")])]
    return s

out = []
with patch("app.services.cpor.portfolio_intelligence.load_evidence_basis_by_case", return_value={1: "none"}), patch("app.services.cpor.incremental_unit_cost.build_portfolio_incremental_summary", return_value={"marker": "unfiltered"}) as summary:
    for kwargs in ({}, {"tenant_id": "fictional"}, {"customer_id": 7}, {"bu": "NB"}, {"include_incremental": False}, {"tenant_id": "fictional", "include_incremental": True}):
        summary.reset_mock()
        result = build_portfolio_intelligence(session(), **kwargs)
        expected_call = not kwargs
        assert summary.called == expected_call, kwargs
        assert (result["incremental_unit_cost"] is not None) == expected_call, kwargs
        out.append({"kwargs": kwargs, "summary_called": summary.called, "support_usd": result["totals"]["support_usd"]})
print(json.dumps(out, indent=2))
