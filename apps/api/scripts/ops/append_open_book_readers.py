"""Append the open_order / line_state reader list to the discovery note.

Prints a count only. Does not open a database.
"""

from __future__ import annotations

from pathlib import Path

API = Path(__file__).resolve().parents[2]
REPO = API.parents[1]
OUT = REPO / ".eif" / "audit" / "OPEN_BOOK_20261028" / "discovery.txt"

VERDICT = """
=== 1b. Readers of open_order or line_state ===

Closing does not add a column. line_state becomes closed_shipped or
closed_disappeared. Both fit varchar(32). A reader that already requires
line_state = open_order, or line_state = shipped, does not count a closed
fact. Readers that keep every non-open row (keep_counted_line) or that count
status <> received needed an explicit exclusion.

Changed so a closed fact is not an open line:
- app/services/supply_overview.py headline WHERE. open_lines was status distinct
  from received. Pipeline was already line_state = open_order.
- app/services/brief_signals.py inbound_not_received_count_stmt.
- app/api/v1/endpoints/shipping.py the lines grid, the ETA fact scope, and the
  summary. still-to-ship already requires line_state = open_order.

Already exclude a closed fact, no code change:
- app/query/model/rules.py shipment open quantity and open counts require
  line_state = open_order. A closed row contributes 0.
- app/services/shipment_strict_pair.py is unchanged. Its window is only
  shipped and open_order, so a closed row is not a twin and is not an open
  remainder. keep_counted_line keeps any row that is not an open order, which
  is why the three callers above exclude closed beside it.
- app/services/channel_ops_derived_stock.py counts shipped lines with a POD
  after the snapshot. A closed row is not shipped. Reclassifying a shipped
  row with no confirm date removes it from that sum only when it also has a POD.
- app/services/commercial_planner/lineup_po_reconciliation.py,
  lineup_po_auto_link.py, lineup_bulk_rederivation.py, lineup_po_gap.py and
  po_management.py count open_order or shipped, not a closed state.
- app/services/lineup/net_requirement.py keeps open_order and pipeline.
- app/services/commercial_planner/inbound_lineup_quarter.py returns no bucket
  for a state other than open, shipped or arrived.
- app/services/imports/shipment_plan_d_cutover.py and the sell-through stock
  gap filters count shipped only.
- app/services/imports/shipment_invoice_graduation.py supersedes a shipped
  observation only. An open observation stays. An open-then-shipped pair is
  still the graduated event.
- app/services/imports/shipment_change_events.py leaves date_slip, qty_change,
  graduated and pod_reversal on the observations that are not close markers,
  then emits closed_shipped or closed_disappeared from the marker.

Not an open-book counter:
- app/services/imports/shipment_inbound_facts.py writes facts. A row that is
  not shipped uses the open upsert. Closed rows are not sent through it. A
  report older than the applied book skips the write, so it cannot reopen a
  closed fact.
- app/services/imports/import_job_delete_figures.py removes facts by the job
  that loaded them, whatever the line state. That is the existing delete.

File and line for every apps/api occurrence of open_order or line_state follows.
"""


def main() -> int:
    rows: list[str] = []
    for path in API.rglob("*.py"):
        if ".venv" in path.parts or "__pycache__" in path.parts:
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        for number, line in enumerate(text.splitlines(), start=1):
            if "open_order" in line or "line_state" in line:
                rel = path.relative_to(REPO).as_posix()
                rows.append(f"{rel}:{number}:{line.strip()[:200]}")
    with OUT.open("a", encoding="utf-8") as handle:
        handle.write("\n")
        handle.write(VERDICT)
        handle.write(f"\noccurrences={len(rows)}\n")
        handle.write("\n".join(rows))
        handle.write("\n")
    print(f"occurrences={len(rows)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
