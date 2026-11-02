# Plan: remove the 3 leaked `AUD-PARI-*` facts from `cip` (not run; needs Warren's go)

**What they are.** Three shipped facts written into the real `fact_inbound_shipment` by `tests/test_data_integrity_audit.py` on 2 July (ids 99964, 99966, 99968 on `cip` on 2 November 2026; item code `AUD-PARI-<token>`, no import job, no evidence line, report type `shipped`, 30 units in all). The 29 October one-off close reclassified them to `open_order` (they had no ship confirm date), so they count in open units. B1/M1/M2 did not touch them. Source: GOV-008 review `FINDINGS.md`, "One-off close on cip".

**What was built (not run on any database but `cip_test`).** `apps/api/scripts/ops/remove_leaked_test_shipment_facts.py`:

- Dry run is the default: one READ ONLY transaction; prints the matched ids, units, states.
- `--apply` needs `--expect-db <name>` equal to `current_database()` and `--expect-count N` (default 3) equal to the number of facts matched; it refuses if anything else points at one of them (`superseded_by_fact_id`).
- It writes ONE `platform_audit_event` (`leaked_test_shipment_facts_removed`) holding every removed row in full, then deletes exactly those rows, in one transaction.
- Selection, all three must hold: `item_code LIKE 'AUD-PARI-%'`, `import_job_id IS NULL`, `shipment_evidence_line_id IS NULL`.
- Tests: `apps/api/tests/test_batch2_aud_pari_cleanup.py` (on `cip_test`, rolled back).

**Clone-proof sequence (nothing below has been run).**

1. Clone `cip` to a throwaway database `cip_pari` with a read-only dump: `pg_dump` of `cip`, restore into a new empty database. (Same method as the earlier clones; the guard denies `DROP DATABASE`, so the clone is dropped by hand afterwards. `cip_otw`, `cip_retire`, `cip_retire2`, `cip_retire3` are still in Postgres from before.)
2. Dry run on the clone: `python apps/api/scripts/ops/remove_leaked_test_shipment_facts.py --expect-db cip_pari`. Expect `matched: 3`, `units: 30`, `ids: [99964, 99966, 99968]`, `line_states: ["open_order"]`. If the count or ids differ, stop and re-plan.
3. Record "before" on the clone: open lines and units, shipped lines and units (the figures `scripts/ops/close_open_book.py` `_BOOK_SQL` prints).
4. Apply on the clone: `... --expect-db cip_pari --apply --expect-count 3`. Expect `deleted: 3`.
5. Second dry run on the clone: `matched: 0`. "After" figures: open lines 3 fewer and open units 30 fewer than "before"; every other figure unchanged. Check the audit event holds the three rows.
6. Only then, with Warren's explicit go: dry run on `cip` (`--expect-db cip`), compare with step 2, then `--apply --expect-db cip --expect-count 3`, then a second dry run (0). No restart or migration is involved.
7. Drop the clone by hand.

**Why not just delete by id.** The script matches by what the rows are (test token, no job, no evidence line) and checks the count, so a changed table cannot make it delete something else. The ids are only a cross-check against the review.

**Not done:** none of steps 1-7. `cip` was not written.
