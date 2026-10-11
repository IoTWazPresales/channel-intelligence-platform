# N-0065 shipment-evidence scope, 2026-10-11

Read-only. `current_database()` = cip. Alembic `20261011_0032` (includes `20261009_0026` and `20261009_0027`).

`shipment_evidence_current` is `security_invoker` and its definition calls `cip_sev_current_observation_ids()`.

A planner with no product lines saw 0 current rows.

A planner scoped to the single largest `dim_product.product_line` saw 8758 current rows. Of those, 0 joined to a product on a different line. 1 row had no product; its lineage product is on the scoped line (inherited this line 1, other line 0, no lineage 0).

The 2026-10-08 behavioral fail (a scoped user still saw other lines through the view, under migration 0025) does not reproduce on the current database.
