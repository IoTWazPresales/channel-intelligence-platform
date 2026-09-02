# CURRENT state

**Last updated:** 2026-09-02 (full-platform reconciliation audit complete)

**Branch:** `feat/ns-2-brief-nav-collapse`

**Last content pin:** `a3ee26d` (confirm HEAD with `git rev-parse` after commit)

**Alembic (code):** `20260902_0020` (N-0006 FX enforcement)

**Alembic on cip:** `20260902_0020`

## On feat/ns-2-brief-nav-collapse

- **Programme:** PRG-20260831T145514 rev **166**; log events **166** (SHA256 `0f56b1bb58aef8e6ec119a1172940ac53a525446b42e69152ad9860e18223573`).
- **N-0008** **`complete`** — review run `NS4_INDEPENDENT_REREVIEW_20260902` / `gov-008`; `implementation_run` `NS4_SETTLEMENT_IMPL_20260902` preserved; gates_valid **true**; independence_issues **[]**.
- **N-0006** programme ledger still **`proposed`** — product shipped at `92f8edb` / Alembic `20260902_0020`; **no first-class historical reconciliation path** in programme runtime (Warren decision required).
- **N-0004**, **N-0007**, **N-0009**, **N-0012** complete.

## Programme frontier

- **N-0006** NS-1b FX — ledger sync blocked pending Warren reconciliation decision
- **N-0010** Response — proposed (dependency N-0008 now complete)
- **N-0011** Steward — proposed

**Review evidence:** `.eif/audit/NS4_SETTLEMENT_20260902/independent-rereview.md`

**Deferred hygiene:** BACKLOG-156 (Lineup inert scope bar); BACKLOG-157 (design-language interaction honesty).

**Full-platform reconciliation:** performed 2026-09-02 — authoritative matrix at `docs/design/CIP_FULL_PLATFORM_RECONCILIATION.md` (BLN-0001 baseline `46368f6`; 50 capabilities reconciled; 0 RETIRE; 10 API-without-UI gaps). Warren reviews before RESTORE/RETIRE/IA commitments.

**Env:** local Windows. Web `:3000` + API `:8001`.
