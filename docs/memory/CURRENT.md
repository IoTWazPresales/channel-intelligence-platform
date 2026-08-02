# CURRENT state

**Last updated:** 2026-08-02 (commercial foundation: POD + YoY + OPEN_CHANNEL)

**Branch:** `fix/commercial-foundation-pod` · prior schedules work remains on `feat/report-schedules-beat` (PR #17) tip `2ae6192` pushed

**Alembic:** `20260802_0009` on cip / code head (sticky POD view)

## Done (this session)

- **Push** `2ae6192` (WoC regression) to `feat/report-schedules-beat`.
- **BACKLOG-088 / P1-D004:** sticky POD on observation + fact upsert + `shipment_evidence_current` view; fact backfill **5961** rows (156 remain without evidence POD). Census: fact shipped POD **12973** / null **156**.
- **Schema drift Q1:** `commercial_sku_assumption` ORM ≡ DB (no `target_srp_local` on SKU — SRP lives on plan lines). No migration needed. SKU economics steward-only.
- **YoY coverage (A3-04):** empty current quarter → `has_data=false`, YoY null + vintage (not −100%).
- **OPEN_CHANNEL:** id **19** already merged; **5013** absorbed via dedicated `open_channel_absorb` after clone-proof `cip_oc_absorb_smoke` PASS, then `--apply-cip`.
- **COMMERCIAL_SEMANTICS:** B2-01..04 + B4-01 SPEC rows; A3-04 coverage rule.
- **Q5:** `purchase_order` is header-only; in-transit qty = `open_order` + shipped-not-landed.

## Next

1. A2-U1 already marked IMPLEMENTED for A2-01/02/06 — confirm whether Warren meant A2-04/05 SPEC next, or stop.
2. Merge PR #17 / #16 when ready; B-lane UI only after SKU economics steward seed.
3. Remaining residual: P4–P6 / Q-004 CST formats.

**Env:** local Windows. API `:8001`, web `:3000`.
