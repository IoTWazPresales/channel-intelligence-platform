"""One-time backfill: customer_po + purchase_order from historical shipment raw_source_row.

Dry-run by default. Warren runs with --confirm after migrations 0052–0054.
"""

from __future__ import annotations

import argparse

from sqlalchemy import select, text

from app.db.session_sync import SessionLocal
from app.models.shipment_evidence import ShipmentEvidenceLine
from app.services.imports.cip_db_identity import is_cip_application_database
from app.services.imports.shipment_field_mapping import extract_customer_po_from_raw_row
from app.services.imports.shipment_po_normalization import normalize_po_number
from app.services.imports.shipment_purchase_order_materialize import upsert_observed_purchase_order


def run(*, confirm: bool) -> dict[str, int]:
    stats = {
        "rows_inspected": 0,
        "customer_po_found": 0,
        "purchase_orders_upserted": 0,
        "lines_updated": 0,
        "no_po_column": 0,
    }
    with SessionLocal() as db:
        dbname = db.scalar(text("SELECT current_database()"))
        if not is_cip_application_database(str(dbname)):
            raise SystemExit(f"Refusing: current_database()={dbname!r} is not CIP")

        lines = list(
            db.scalars(
                select(ShipmentEvidenceLine)
                .where(
                    ShipmentEvidenceLine.customer_po.is_(None),
                    ShipmentEvidenceLine.raw_source_row.is_not(None),
                )
                .order_by(ShipmentEvidenceLine.id)
            ).all()
        )
        stats["rows_inspected"] = len(lines)

        for line in lines:
            raw = line.raw_source_row if isinstance(line.raw_source_row, dict) else {}
            extracted = extract_customer_po_from_raw_row(raw)
            if not extracted:
                stats["no_po_column"] += 1
                continue
            stats["customer_po_found"] += 1
            norm = normalize_po_number(extracted)
            if not norm:
                continue
            if not confirm:
                continue
            po_id = upsert_observed_purchase_order(
                db,
                po_number_raw=extracted,
                po_number_norm=norm,
                distributor_id=int(line.distributor_id) if line.distributor_id is not None else None,
            )
            stats["purchase_orders_upserted"] += 1
            line.customer_po = extracted
            line.purchase_order_id = po_id
            db.add(line)
            stats["lines_updated"] += 1

        if confirm:
            db.commit()
        else:
            db.rollback()

    return stats


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--confirm",
        action="store_true",
        help="Write changes (default is dry-run: counts only).",
    )
    args = parser.parse_args(argv)
    stats = run(confirm=bool(args.confirm))
    mode = "CONFIRM" if args.confirm else "DRY-RUN"
    print(f"[{mode}] backfill_shipment_customer_po")
    for k, v in stats.items():
        print(f"  {k}: {v}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
