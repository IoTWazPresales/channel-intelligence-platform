# CURRENT state

**Last updated:** 2026-09-02 (N-0008 NS-4 remediation — scope bar + settle clone proof)

**Branch:** `feat/ns-2-brief-nav-collapse`

**Last content pin:** confirm HEAD with `git rev-parse` after commit

**Alembic (code):** `20260902_0020` (N-0006 FX enforcement)

**Alembic on cip:** `20260902_0020`

## On feat/ns-2-brief-nav-collapse

- **Programme:** PRG-20260831T145514 rev **158**; log events **158** (verify with `program.py verify`).
- **N-0008** `in_progress` @ **verify** — remediation run `NS4_SETTLEMENT_REMEDIATION_20260902`; `ux`/`content` **pending** (await fresh gov-008 re-review); `implementation_run` `NS4_SETTLEMENT_IMPL_20260902` preserved; gates_valid **false**.
- **N-0006** programme ledger still **`proposed`** — product shipped at `92f8edb` / Alembic `20260902_0020`; **no first-class historical reconciliation path** in programme runtime (Warren decision required).
- **N-0004**, **N-0007**, **N-0009**, **N-0012** complete.

## Programme frontier

- **N-0008** NS-4 Settlement — remediation implemented; **ready for fresh independent re-review** (not complete)
- **N-0006** NS-1b FX — ledger sync blocked pending Warren reconciliation decision
- **N-0010** Response — blocked on N-0008 programme-valid
- **N-0011** Steward — frontier

**Remediation evidence:** scope bar honesty in `SettlementScopeBar.tsx`; settle confirm clone test `apps/api/tests/test_cpor_settle_confirm_clone.py` on `cip_ns4_settle_clone`.

**Env:** local Windows. Web `:3000` + API `:8001`.
