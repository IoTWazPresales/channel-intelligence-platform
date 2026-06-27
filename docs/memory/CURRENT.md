# Current state

**Last updated:** 2026-06-27 (DSI customer alias resolution-key fix; job #96 unblocked)
**Verify git:** `git branch --show-current` · `git rev-parse --short HEAD`

---

## Branch and delivery

| Field | Value |
|-------|--------|
| **Branch** | `feat/dsi-async-topology` |
| **HEAD (snapshot)** | `cac1919` — local working tree has uncommitted DSI alias-key fix |
| **PR** | None open — open when soak complete |
| **Alembic (code)** | `20260623_0050` |
| **Alembic (DB)** | **`20260623_0050`** on local `cip` (migration run 2026-06-24) |

---

## Database and environment

| Field | Value |
|-------|--------|
| **Active DB** | Local Postgres `cip` @ `127.0.0.1:5432` (topology B) |
| **Bitemporal flags** | `CIP_SHIPMENT_BITEMPORAL_DUAL_WRITE` / `_READ` — **off** by default |

---

## Dev topology

Local desktop (no Docker): `pnpm dev:api` :8001, `pnpm dev:web` :3000, worker or `CIP_DEV_CELERY_DISPATCH=in_process_thread`.

---

## What is working

### Shipment import wizard (DSI-aligned — wired + unit-tested)
- **7 steps:** upload → column mapping → validate & resolve → apply.
- **Apply step:** `ImportJobLoadedSuccessCallout` when job stage `loaded`.
- **`shipmentWizardActiveStepFromServer`** — revisit jobs land on correct step.
- **Validate progress** — re-validate on `validated` jobs shows progress.
- **Steward grid** — `filterShipmentStewardCandidates` / `ShipmentImportJobResolutionSection` DSI parity (tabs, plan toolbar, bulk steward, server re-validate).

### Plan C / D / BACKLOG-007 (prior)
- Resolution plan API, paginated candidates, bitemporal D1–D3 (schema + dual-write wired; flags off), post-validate re-map + orphan purge.

### DSI customer alias resolution-key fix (2026-06-27) — uncommitted
- **Root cause:** DSI staging resolves customers on the **Dealer Name Group** token
  (`effective_dsi_customer_primary_for_resolution`), but the steward map / provisional /
  open-channel apply paths wrote the approved alias keyed on the **customer-name** column
  (`_source_customer_alias_raw_for_dsi_candidate`). When the two columns differed, the
  resolver looked up a token the alias was never stored under → permanent
  `customer_unresolved`, while the candidate was marked `resolved` (terminal) and hidden
  from the Customers tab. Phantom-resolved loop = "40 rows still need fixing, nothing in
  Customers tab".
- **Fix (Part A, source):** new `dsi_customer_alias_normalized_token(cand)` = candidate
  resolution identity (`normalized_key`, dealer-group primary). Routed `scope_key_for_dsi_candidate`,
  map sync/async, provisional create, open-channel, preview through it. Alias `normalized_token`
  now matches the resolver lookup.
- **Fix (Part B, safety net):** `process_distributor_sales_inventory` preserve logic no longer
  carries a stale `resolved` status onto a regenerated `customer_dealer_token` candidate
  (regeneration ⇒ row still unresolved). Re-opens as `needs_review` with
  `ctx.prior_resolved_customer_id` hint; `ignored`/`waived_open_channel`/`acknowledged_unique`
  still preserved. Dormant on healthy jobs (correctly-resolved candidates do not regenerate).
- **Job #96 remediation:** re-wrote the 4 phantom aliases under the dealer-group key via the
  fixed canonical writer; full revalidate (178k rows) → **blocking_rows = 0**
  (human_fixable / master_merge / steward_map all 0). Ready for Continue to apply → SOH load.
- **Tests:** `test_dsi_bulk_map_customers_scope.py` (added dealer-group keying regression +
  distinct-identity), `test_dsi_bulk_provisional_customers_reuse.py` (distinct dealer groups).
  Pre-existing dev-DB-pollution failures in `test_distributor_sales_inventory_import.py` are
  unrelated (see `.pytest_cache lastfailed`).

### Docs / backlog (2026-06-24)
- **BACKLOG-046** — ACZA BOM Not Ready sheet handling (operator workaround: upload Shipped + Unship only).
- **BACKLOG-047** — stale column-mapping UI after Back + re-upload.
- **BACKLOG-048** — Celery + background-task parity audit.
- **BACKLOG-045** — steward UI parity audit (side drawer + workspace layout).

---

## In progress / not proven live

- Warren **actively working through** ACZA shipment upload / steward workflow (20260623 file; BOM tab deferred per BACKLOG-046).
- Browser soak on shipment wizard end-to-end not yet confirmed this session.
- Rectron / distributor-vs-customer mapping and 0.85 auto-apply threshold — reported in lost session; **not re-verified** after `a04e4d5`.
- Import Centre home URL reset on navigate — reported; fix in `a04e4d5` **not re-verified** live.
- Plan D D4–D5 deferred; bitemporal read path not exercised with flags on.

---

## Next (recommended)

1. Finish current ACZA upload workflow (trim workbook to **Shipped + Unship** until BACKLOG-046).
2. **Smoke:** shipment wizard upload → map → validate → steward → apply on local.
3. **ACZA 2023 backfill** per `docs/SHIPMENT_EVIDENCE_OPERATOR.md` (latest-job-wins; older file won't overwrite newer `source_key` rows).
4. Open PR on `feat/dsi-async-topology` when soak passes.

---

## Blockers requiring Warren

- Business sign-off: should **BOM Not Ready** ever enter shipment facts? (BACKLOG-046)
- Main promotion — explicit instruction only

---

## Key references

| Topic | Doc |
|-------|-----|
| Import contract (shipment) | `docs/IMPORT_FLOW_CAPABILITY_CONTRACT.md` |
| Operator | `docs/SHIPMENT_EVIDENCE_OPERATOR.md` |
| Plan D | `docs/SHIPMENT_BITEMPORAL_PLAN_D.md` |
| Backlog 046–048 | `docs/BACKLOG.md` |
