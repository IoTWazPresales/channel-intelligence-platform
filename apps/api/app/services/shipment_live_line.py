"""The one "live line" rule for ``fact_inbound_shipment`` (GOV-008 review 2 Nov, B1).

A fact is live unless its ``line_state`` is one of the closed states the open-book close,
the PO-less twin retire and the orphan retire write: ``closed_shipped``,
``closed_disappeared``, ``closed_moved``, ``closed_superseded``. A closed fact stays in
the table as history; it is not shipped, not inbound and not open. Every reader that
totals or lists shipment facts as current business uses this rule and no reader spells
the list itself.

- ORM / Core predicate: :func:`live_line` (takes the ``line_state`` column, so it works on a
  mapped class, an alias or a compiled-model table).
- Raw SQL: :func:`live_line_sql` (takes the SQL expression of the column).
- ``app.services.imports.shipment_open_book.exclude_closed_inbound`` is this rule for a mapped class.

This module imports no database models, so any reader can import it without a cycle.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import func

from app.services.imports.shipment_evidence_report_detect import CLOSED_LINE_STATES

# Sorted so the SQL text is stable (plan cache, test snapshots).
_CLOSED_SORTED = tuple(sorted(CLOSED_LINE_STATES))


def live_line(line_state_column: Any):
    """SQLAlchemy predicate: the fact is still on the book (not closed in any way)."""
    return func.lower(func.coalesce(line_state_column, "")).notin_(_CLOSED_SORTED)


def live_line_sql(line_state_expr: str = "fact_inbound_shipment.line_state") -> str:
    """SQL text of :func:`live_line` for raw queries. ``line_state_expr`` is trusted code, never user input."""
    states = ", ".join(f"'{s}'" for s in _CLOSED_SORTED)
    return f"lower(coalesce({line_state_expr}, '')) NOT IN ({states})"


def is_live_state(line_state: str | None) -> bool:
    """Python form of the same rule, for code that already holds a row."""
    return (line_state or "").strip().lower() not in CLOSED_LINE_STATES
