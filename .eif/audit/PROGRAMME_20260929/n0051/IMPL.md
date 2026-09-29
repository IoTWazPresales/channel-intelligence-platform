# N-0051 import-complete merged-id check

`run_import_complete_rail` is the side-effect rail after DSI and shipment apply have already committed `status=completed` / `stage=loaded`.

The check calls `customer_leftover_repair.leftover_row_total_across_merged_losers` (customer FKs, including `customer_source_token_alias`, skipping `merged_into_customer_id`) and the same skip rule for distributor FKs (including `distributor_source_token_alias`).

A non-zero total writes `ImportRowResult` severity `warning`, code `merged_id_leftover`, and stamps `staged_metadata.merged_id_leftover.flagged=true` with `blocks_apply=false`. Status and stage are not changed. A scan failure is logged and rolled back; report fan-out still runs; apply stays complete.

Proof:

- pytest `tests/test_merged_id_leftover_check.py`: 3 passed (zero does not flag; non-zero is warning; failed scan still fans out and leaves the job completed).
- Read-only `measure_merged_id_leftovers` on `cip_test` (`current_database()=cip_test`): customer 0, distributor 0, total 0. No write, no commit.
