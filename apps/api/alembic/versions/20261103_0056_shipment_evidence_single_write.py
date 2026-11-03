"""Shipment evidence D4: the line stops carrying the observation payload.

Revision ID: 20261103_0056
Revises: 20261103_0055
Create Date: 2026-11-03

Plan D step D4 (BACKLOG-057-D4, node N-0098). The shipment loader writes the parsed payload once, to
``shipment_evidence_observation``; ``shipment_evidence_line`` keeps the job scope and the steward state. Three changes:

1. ``report_type``, ``line_state`` and ``raw_source_row`` on ``shipment_evidence_line`` lose NOT NULL. The loader no longer
   inserts them. Existing rows keep their values (no data is touched; D5 drops the columns).
2. ``ix_shipment_ev_obs_evidence_line (evidence_line_id, id DESC)``. A line's payload is its newest observation
   (``evidence_line_id = line.id ORDER BY id DESC LIMIT 1``); that lookup had no index.
3. ``shipment_evidence_current`` is re-issued without the line's ``pod_date`` term in the ``pod_date`` COALESCE. The line no
   longer carries a POD; the sticky-POD subquery over observations already supplies the carried-forward value.

Apply this migration BEFORE deploying the D4 code (the new loader inserts lines without the three relaxed columns).
The downgrade restores NOT NULL (it fails if a D4 line has no payload; back-fill from the observation first), drops the
index and re-issues the 0026 view. NOT APPLIED to ``cip``.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Sequence, Union

from alembic import op

revision: str = "20261103_0056"
down_revision: Union[str, Sequence[str], None] = "20261103_0055"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

INDEX_NAME = "ix_shipment_ev_obs_evidence_line"
RELAXED_COLUMNS = ("report_type", "line_state", "raw_source_row")
_LINE_POD_TERM = "        sel.pod_date,\n"


def _view_0026():
    path = Path(__file__).with_name("20261009_0026_shipment_evidence_lineage_rls.py")
    spec = importlib.util.spec_from_file_location("_view_0026", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def upgrade() -> None:
    for col in RELAXED_COLUMNS:
        op.execute(f"ALTER TABLE public.shipment_evidence_line ALTER COLUMN {col} DROP NOT NULL")
    op.execute(
        f"CREATE INDEX IF NOT EXISTS {INDEX_NAME} ON public.shipment_evidence_observation "
        "(evidence_line_id, id DESC)"
    )
    m = _view_0026()
    sql = m.VIEW_SQL.format(current_filter=m.CURRENT_FILTER)
    if _LINE_POD_TERM not in sql:
        raise RuntimeError("0026 view no longer has the line pod_date term; the 0052 re-issue must be revisited")
    op.execute(sql.replace(_LINE_POD_TERM, "", 1))


def downgrade() -> None:
    m = _view_0026()
    op.execute(m.VIEW_SQL.format(current_filter=m.CURRENT_FILTER))
    op.execute(f"DROP INDEX IF EXISTS public.{INDEX_NAME}")
    for col in RELAXED_COLUMNS:
        op.execute(f"ALTER TABLE public.shipment_evidence_line ALTER COLUMN {col} SET NOT NULL")
