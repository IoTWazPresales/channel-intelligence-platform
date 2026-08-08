# CURRENT state

**Last updated:** 2026-08-08 (BACKLOG-127/128 on feature branch)

**Branch:** `feat/backlog-127-128-dap-case-po` (from `main` @ `5cf513b`)

**Alembic:** `20260807_0010` — applied on local `cip` (no new migration)

## Done

- **PR #18 / #19 / #20 MERGED** on main (Unit 6c+6f, 124, 125/126).
- **BACKLOG-127 / D-041:** Phase-2 confirmer — unique ship `unit_price` within 2% of
  line `dap_evidence_local` → `confirm_price` / `conflict_price` / `offer_accept_price`.
  No DAP column invented; never margin→DAP.
- **BACKLOG-128:** `…/case-po-attribution-gap/preview|apply` — unique PO covering
  attributed products; never clears attribution. cip: case **114** ↔ PO **10473** (Stylus).

## Next

1. Commit + PR when Warren asks; merge before roadmap.
2. Roadmap A1∥A2∥A3 when Warren clears the mandate gate.
3. Optional: run confirmer apply for price actions after steward review of offers.

**Env:** local Windows. `cip` @ `20260807_0010`.
