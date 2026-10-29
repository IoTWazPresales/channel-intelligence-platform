# Import friction — findings (29 Oct 2026)

Source: a Cursor session's read-only census on `cip` at `440916c3`, copied into the repo by Claude (claude.ai chat). That session's edits were refused by the session control plane before any code change. Its scratch query scripts are in this folder and stay uncommitted.

## Jobs (all source 6, read-only on cip)

| Job | File | Stage | Created → completed |
|---|---|---|---|
| 1339 | ACZA Shipped Unshipped 20260911.xlsx | loaded | 357 s |
| 1695 | ACZA Shipped Unshipped 20260929.xlsx | loaded | 3,251 s |
| 1696 | ACZA Shipped Unshipped 20261023 (1).xlsx | loaded | 2,337 s |
| 1697 | ACZA Shipped Unshipped 20261027.xlsx | validated, not loaded | 523 s |

These wall-clock figures include Warren's manual steps (mapping confirm, sheet dialog, stewarding, Apply). They are **not** measured stage times. The shipment path has no per-stage timer, so speed is still unmeasured. The earlier "13 min 18 s validation" figure for 1695 is withdrawn.

## Findings

1. **Listing poll blocks imports.** `listing_capture.poll_listings` is not routed and uses the default `celery` queue. The Windows worker is one solo process subscribed to `interactive,batch,celery`. A poll (about 5 min every 30 min) occupies it, and an import waits behind it. Fix: a separate listing queue with its own consumer.
2. **Mapping step stops every upload.** A saved header mapping is applied when the file is read, but the Import Center still stops on the mapping step before validation.
3. **Sheets are remembered only per job.** 1696 confirmed Unship + Shipped. 1697 confirmed those plus BOM not ready, so the 27 Oct file showed the dialog under the current rule. Closing the dialog runs sheet inference inside the request and shows no progress or elapsed time.
4. **Repeat stewarding.** Job 1697 has 12 customer tokens in `needs_review`. All 12 were resolved on job 1696 with `steward_map_existing_customer` (8 to customer 121, 4 to customer 1); none is new. Candidates are deleted and rebuilt for each job. A map writes an approved customer alias, and later scoring looks the alias up by the normalised source token, yet these 12 still came back. Hypotheses to test, not yet proven: (a) the normaliser used when the alias is written differs from the one used at lookup (the known name-normaliser hierarchy defect class); (b) noise and internal-note rows are keyed by a hash (`sc:` / `in:`), not the token, so their alias can never match.
5. **Special-case clears are not remembered.** A clear edits that job's candidate only. The next load runs the name normaliser again: a remainder in the noise-word list becomes `noise_only`, and text after a comma becomes `internal_note`. Job 1695 had 6 (2 internal note, 4 noise), 1696 had 0, and 1697 has 4 `noise_only` rows back in `needs_review`, all within the 12 above. No tenant-level clear is stored per token or item code.
6. **Bulk map asks for a typed Customer ID or Distributor ID** (`apps/web/src/app/(app)/admin/shipment-evidence/ShipmentBulkActionInlineForm.tsx`).

## Not yet done

- The proof that a job submitted during a poll starts within 10 seconds.
- Stage timing of the 29 Sep file on cip_test.
- Any code change for 1–6.
