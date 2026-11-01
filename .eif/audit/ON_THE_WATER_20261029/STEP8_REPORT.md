# On the water — steps 6 to 8 (1 Nov 2026). STOPPED: waiting for Warren's "run against cip"

Nothing has been run against `cip`. `cip` is read from only (schema reports, header counts, one pg_dump).

## What exists

| Step | Result | File |
|---|---|---|
| 6 Path map | Shipments tab, KPI tiles and grid filters, `observation_transitions.py`, `shipment_change_events.py`, mapping catalogue, tenant overrides, workbench-ui, readers; contradictions | `PATH_MAP.md` |
| 7 Drift | `uq_fact_inbound_shipment_fact_upsert_key` declared in `app/models/facts.py` and added to `cip_test` (cip has it); the cip indexes declared; the twin `..._import_job_id` indexes removed; other drift listed, unchanged | `schema_drift.txt`, `apps/api/scripts/ops/schema_drift_report.py` |
| 8 Migration | `20261101_0049_on_the_water.py`: 12 nullable columns on the three shipment tables, append-only `port_condition`, the drift fixes (each only where missing). Applied to `cip_test` (head `20261101_0049`, 0 drift on these tables) | `apps/api/alembic/versions/20261101_0049_on_the_water.py` |
| 8 Writers | Mapping targets and header aliases, importer, observation copy, fact writer, `shipment_voyage.py`, tenant key `shipping_method_pattern` | see commit |
| 8 Backfill | `scripts/ops/backfill_shipment_water_fields.py`: dry run by default, `--apply --expect-db`, one transaction, counts checked against the plan, one `platform_audit_event`; fills only NULL columns | script |
| 8 Clone proof | pg_dump clone of `cip` (`cip_otw`): ALL PASS (22 checks), per job and per field | `backfill_clone_proof.txt` |

## Clone proof, in short

Rows: 110,834 evidence lines, 112,232 observations, 15,788 facts. After the apply, per field (lines / observations / facts):
on_board_date 99,099 / 99,139 / 13,249; port_eta_date 99,099 / 99,139 / 13,249; port_ata_date 97,188 / 97,188 / 13,021;
shipping_method 110,832 / 112,230 / 15,783; forwarder_code the same; origin_hub 110,537 / 111,916 / 15,704;
ship_way 110,834 / 112,232 / 15,785; deliver_port 110,832 / 112,230 / 15,783; container_no 0 (the ACZA "Container Number" is never mapped).
Per-job counts (14 jobs, plus facts with no job) are in the proof file. Every other column of every row, including each
observation's `source_row_hash`, is byte-identical; a second apply plans nothing; downgrade with the data present and a second
apply give the same counts; a forced failure rolls everything back. The first attempt rolled back safely on a bug of mine
(a streaming cursor stuck on the connection); fixed, and the proof rerun from the start (`backfill_clone_run_attempt1_failed.log`).

## Tests

- New: 21 unit tests (`test_shipment_voyage.py`, the pattern override in `test_commercial_tenant_profile_p6_persistence.py`) and 3 DB tests on `cip_test` (`test_shipment_water_db.py`): all pass.
- Full API suite on `cip_test`: 3,463 passed, 23 skipped, 16 failed and 28 errors on the first run from the repo root. The 28 errors and 5 failures were my invocation (Alembic needs `apps/api` as the working directory) and two stub lines my writers read too strictly (fixed). Rerun from `apps/api`: 11 failures remain, none in files this change touches:
  - `test_shipment_open_book.py` (5): `cip_test` holds committed copies of the 29 Sep, 23 Oct and 27 Oct reports from the 30 Oct import work, so a report dated 11 Sep is "older than the applied book" and closes nothing.
  - `test_shipment_apply_background.py`, `test_shipment_apply_hardening.py` (3): patch `upsert_inbound_shipment_facts_for_job`, removed from `shipment_apply_sync` in `bbde4f95`.
  - `test_query_v2_api.py::test_catalog_v2_shape`, `test_dashboard_v2_definitions.py` (2): expect week as the lowest grain; the E8 day grain (`a4118c30`) changed it.
  - `test_sell_through_dimensions_db.py` (1): sees extra committed customers in `cip_test`.
  Not run on the parent commit; the classification is from the failure messages and `git log`.
- Web: 219 files / 1,173 tests, tsc, lint and build as in the Part 1 report.

## Needs Warren's call

1. **Forwarder pattern.** The SPEC default ("leading capitals") left 3,834 of 110,832 lines (forwarder written in Chinese) and 267 (no hub) without forwarder or hub. The default now reads capitals or non-Latin letters and makes the hub optional (`DEFAULT_SHIPPING_METHOD_PATTERN`, one regex). Same answer on every ASCII value.
2. **`fact_upsert_key` NOT NULL** is on `cip` but not in the model or `cip_test`; `seed_demo.py` and five test modules build facts without it. Left as is, listed in `schema_drift.txt`.
3. **Mapping step asks once more** per source: the new headers are not in the saved mapping.
4. **Not done on purpose:** `_DATE_SLIP_FIELDS` (BACKLOG-218) and the slip "earliest, not previous" query: they would add change events for every existing observation pair the day the backfill lands.
5. `shipment_evidence_current` (a view) does not expose the new columns; recreating it is DDL outside the approved migration.
6. `cip_otw` (the clone) is still in Postgres.

## To apply to cip (only on "run against cip")

Migration as the table owner (`DATABASE_URL_SYNC_MIGRATE`), then `backfill_shipment_water_fields.py` as a dry run, then `--apply --expect-db cip`. No service restart is part of it.
