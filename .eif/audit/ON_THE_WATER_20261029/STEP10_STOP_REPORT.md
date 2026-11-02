# Twins and loader: the combined STOP report (2 Nov 2026)

Nothing here has touched `cip`: every query on it was a read-only transaction. Both proofs ran on fresh pg_dump copies of `cip`
(`cip_retire3` for the final run; `cip_retire`, `cip_retire2` and `cip_otw` are earlier clones, drop them by hand: the guard denies
`DROP DATABASE`). Same session, not independent verification. Logs: `retire_clone_run.log`, `loader_clone_run.log`.

## A. The 63 overdue lines (read-only, before any fix)

63 lines / 6,870 units on 9 vessels: 24 lines / 3,897 units are real (ETAs 27, 29, 30 Oct, still at sea in the 27 Oct file, five
days past the report); 39 lines / 2,973 units are stale facts. A shipped fact written before its purchase order resolved keeps
the key `ship:{delivery|item}`; the same line is now written under `ship:{delivery|item|PO}`, so the old row is never updated again
and keeps counting. The open-book close only touches `open_order` rows, so nothing closes it.

## B. Proof 1: twin retirement (`prove_po_less_retire_clone.py`): ALL PASS

Rule (existing module `shipment_shipped_fact_identity_twin_merge.py`; its collapse deletes the loser of two rows on ONE key and
repoints foreign keys, these twins have TWO keys and must be kept, so the rule sits beside it and shares its module and CLI:
`merge_shipped_fact_identity_twins.py --retire-po-less [--apply --expect-db NAME]`): a shipped fact with no `purchase_order_id` is
superseded when a newer job wrote the same delivery + item (same operating unit) under a PO-inclusive key and the quantities match.
It becomes `line_state = 'closed_superseded'` with `superseded_by_fact_id` and `superseded_by_key` (migration 20261101_0050, two
nullable columns). Every reader that excludes the closed states drops it. Downgrade puts the rows back to `shipped`.

- 47 twins found; **37 retired (2,897 units)**; **10 listed, not retired**, quantity differs.
  Of the 39 stale overdue facts: 37 retired, **2 listed (113211: 40 vs 80; 113224: 36 vs 72)**. The other 8 listed are older, not overdue:
  134343 (36 vs 108), 134344 (108 vs 432), 134345 and 134346 (108 vs 648), 134347 (108 vs 324), 134348 (108 vs 324), 134349 (36 vs 540),
  134350 (12 vs 60). In each the PO-key fact holds more units than the old fact: the old job lost rows to the loader collapse (section C).
- Checks: migration changes no row (fingerprints identical, downgrade and upgrade round trip); dry run read-only; applies refused without or with the wrong
  `--expect-db`; exactly the 37 rows changed, and only in line_state, updated_at and the two pointers; each points at a shipped PO-key fact of a newer job with the same
  delivery + item and a matching quantity; matches an independent SQL reading of the twin set; one audit event; second dry run and second apply retire nothing.
- Writer: `upsert_inbound_shipment_facts_for_job` now retires the PO-less twin of every PO-key fact it writes (same transaction), so this cannot recur; it also
  refreshes the retired rows' pointer, because a reload replaces a fact row (new id, same key).

| Figure | Before | After |
|---|---|---|
| Shipped units (line_state shipped) | 1,370,755 | 1,367,858 |
| Shipped, not landed units | 17,727 | 14,830 |
| Landed units (POD) | 1,353,028 | 1,353,028 |
| Open units / pipeline units | 66,260 / 48,533 | 63,363 / 48,533 |
| Past-ETA lines with no POD | 90 | 56 |
| Fill rate | 0.26187 | 0.26187 |
| On the water: at sea units / lines | 13,516 / 162 | 10,619 / 125 |
| Vessels / overdue vessels | 14 / 9 | 9 / 4 |
| Units on overdue vessels | 6,870 | 3,973 |
| Arrived units | 3,417 | 3,417 |

The 4 overdue vessels left: three are real (ETA 27, 29, 30 Oct); one holds the 2 listed facts (76 units).

## C. Proof 2: the loader (`prove_loader_order_grain_clone.py`): ALL PASS

Defect: the source key of a Shipped row is delivery + invoice line + item. A line not invoiced yet has a blank invoice line, so rows of one
delivery and item on different orders collapsed into one and the others' quantities were lost. In the 27 Oct file: 104 rows / 7,018 units
(47 keys, every one with a blank invoice line, none a true repeat), 60 lines / 4,264 units of them at sea.

Fix (`shipment_evidence_source_keys.py`): with a blank invoice line the key also carries the order and its line (`...|item|ord:<order>|<line>`);
a numbered invoice keeps the key it always had; a row with no order number keeps the old shape. The legacy-key helpers know the new shape.
`line_identity_key` was already order-grain for blank-invoice rows, and the invoice graduation works on that lineage (order, line, item), not on the source key:
the proof shows the graduation finds nothing new, and no PO-less twin appears.

Second defect found by the proof and fixed: the fact writer added up rows of one fact key only inside a 500-row chunk, and a later chunk replaced the key. With new
evidence lines the two rows of `ship:15250542805|90NB16Z2-M002L0|16484` (a landed fact) fell in different chunks and 35 units vanished. Lines of one key are now kept in one chunk
(test added). Landed units are unchanged after the fix.

Re-process (`scripts/ops/reprocess_shipment_job.py --job 1697 [--apply --expect-db NAME]`, dry run default): re-reads the stored workbook with the current loader, rewrites job 1697's
evidence lines, observations and facts, no notification side. It adds the voyage fields to the job's saved mapping (the one-time confirm), because the saved mapping predates them.

| Check | Result |
|---|---|
| Evidence lines of the Shipped sheet | 7,242 → 7,346 = the workbook's rows; units 500,418 → 507,436 = the file |
| **27 Oct position (ship-confirmed, on board ≤ 27 Oct, no ATA, sea)** | **169 lines / 14,278 units** (was 109 / 10,014) |
| At sea by cip's rule as of today, evidence | 197 lines / 14,987 units = the workbook |
| Facts of every other job | unchanged (pointers and updated_at aside) |
| Surviving facts of job 1697 | product, distributor, customer, PO and state unchanged (0 of 7,328) |
| PO-less twins left to retire | 0 (the same 10 listed) |
| Retired facts | still 37, no dangling pointer |
| Guards | dry run writes nothing; refused without or with wrong `--expect-db`; a forced failure rolls everything back |
| Second re-process | no evidence line or fact changes |

| Figure (after twins retired → after re-process) | Before | After |
|---|---|---|
| Shipped units | 1,367,858 | 1,374,481 |
| Shipped, not landed | 14,830 | 21,453 |
| Landed units | 1,353,028 | 1,353,028 |
| Open units / pipeline units | 63,363 / 48,533 | 71,302 / 49,849 |
| Fill rate | 0.26187 | 0.26187 |
| **On the water: at sea units** | 10,619 | **15,063** = 14,987 (workbook) + 76 (the 2 listed twins, not retired) |
| At sea lines (facts) | 125 | 133 (197 evidence lines; a fact adds up one delivery + item + PO) |
| Vessels / overdue vessels | 9 / 4 | 9 / 4 |
| Units on overdue vessels | 3,973 | 4,089 |
| **Arrived, not delivered units** | 3,417 | **5,512** = the workbook's 82 lines |

Things to know before the real run:
- **Observations are append-only and not de-duplicated on a re-process:** +8,059 rows for job 1697 (the old-shape rows stay beside the new); a second re-process adds 329 more
  (customer resolution changes from unresolved to resolved). Evidence lines and facts do not change. Harmless to the figures; it is history volume.
- `import_entity_mapping_candidate` goes 7,044 → 6,925 (the validate stage rebuilds the candidates, earlier decisions are reused). Worth a look at the steward queue after the real run.
- The open book closed 0 facts; no distributor, customer or product moved.
- The loss is not only job 1697 (read-only, every ACZA job on cip, `diag_loss_per_job.log`): rows / units lost per job: 1159 111 / 8,515; 1326 141 / 11,503; 1339 162 / 13,229; 1695 167 / 13,524; 1696 137 / 10,438; 1697 104 / 7,018
  (older jobs 7 to 51 rows). Counting a line once per job it was lost in, 1,005 lines / 72,505 units; **655 later appear invoiced in a newer job (self-healed), 350 never did**
  (they are mostly lines of the newest jobs that are still blank, 104 + 90 + 86, plus 70 older). Re-processing job 1697 recovers its 104; jobs 1695 and 1696 are older than
  the applied book, so their facts would not change (their evidence lines and observations would). I propose re-processing 1697 only.

## D. What "run against cip" would do, in order

1. Migration 20261101_0050 as the table owner (two nullable columns, no row changes).
2. Twin retirement: `merge_shipped_fact_identity_twins.py --retire-po-less` dry run, then `--apply --expect-db cip` (expect 37 retired, 10 listed).
3. Restart worker and API with the new code (writer retires twins at load; new source key).
4. `reprocess_shipment_job.py --job 1697` dry run, then `--apply --expect-db cip`; then the On the water and supply figures as in the proof.
5. Rebuild and restart web (phone-width port names), commit, push.

## E. Open

- The 10 quantity-differs pairs are listed for Warren; the 2 overdue ones keep 76 units at sea until decided.
- Phone-width ports: Shanghai and Chongqing names still touch when vessels sail from both (fixture); needs a design choice.
- Tests: full API suite re-run on the final code and the full web suite are running; targeted shipment tests pass.

## F. Run against cip (2 Nov 2026, after Warren's "run against cip")

Every count matched this report. Outputs: `cip_retire_dry.txt`, `cip_retire_apply.txt`, `cip_reprocess_dry.txt`, `cip_reprocess_apply.txt`, `cip_retire2_dry.txt`,
`cip_retire2_apply.txt`, `cip_measure_before_reprocess.json`, `cip_measure_after.json`, `step10_services.txt`.

| Step | cip | Report |
|---|---|---|
| Target | `current_database()` = cip, `localhost:5432`, role cip; no job running, queue 0, Celery active 0 | |
| 0050 as table owner | cip at 20261101_0050 | |
| Twin dry run / apply | 47 found, 37 to retire (2,897 units), 10 listed; shipped units 1,370,755 → 1,367,858 | same |
| Job 1697 re-process | evidence lines 7,967 → 8,071; facts written 8,071; open book closed 0; the saved mapping gained the voyage fields | same |
| The 10 listed pairs | each PO-key twin equals the sum of its evidence lines in 1697 (2, 3, 4, 6, 6, 3, 3, 7, 2 lines; 80, 72, 108, 432, 648, 648, 324, 324, 540, 60 units): **all 10 retired (700 units), none left** | |
| Retired in all | 47 facts, 3,597 units | |
| At sea | 14,987 units, 131 lines (= workbook 14,987; the 76 from the 2 once-listed overdue facts are gone) | 15,063 / 133 before the 10 |
| Arrived | 5,512 units | 5,512 |
| Vessels / overdue | 8 / 3 (4,013 units on overdue vessels) | 9 / 4 before the 10 |
| Landed units | 1,353,028, unchanged | unchanged |
| Pipeline units | 49,849 | 49,849 |
| Fill rate | 0.26187, unchanged | unchanged |
| Shipped, not landed | 20,753 | 21,453 less the 700 |
| Open units | 70,602 | 71,302 less the 700 |
| Services | restarted once (web, worker, API); `/health/ready` cip; Celery pong; `/supply/shipments` and `/admin/port-conditions` 200 | |

The 10 pairs are retired under `--accept-evidence-sum` (a single PO-key twin that equals the sum of its job's evidence lines); the load-time rule still needs an equal quantity.
