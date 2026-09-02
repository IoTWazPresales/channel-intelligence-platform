# CURRENT state

**Last updated:** 2026-09-02 (N-0008 independent review — FAIL scope bar honesty)

**Branch:** `feat/ns-2-brief-nav-collapse`

**Last content pin:** confirm HEAD with `git rev-parse` after commit

**Alembic (code):** `20260902_0020` (N-0006 FX enforcement)

**Alembic on cip:** `20260902_0020`

## On feat/ns-2-brief-nav-collapse

- **Programme:** PRG-20260831T145514 rev **149**; **N-0008** `in_progress` @ verify — independent review **FAIL** (`ux`/`content` blocked on scope bar); **implementation_run** `NS4_SETTLEMENT_IMPL_20260902` preserved; review run `NS4_INDEPENDENT_REVIEW_20260902` / `gov-008`.
- **N-0004**, **N-0007**, **N-0009**, **N-0012** complete; **N-0006** programme ledger still `proposed` (product shipped; ledger sync deferred).
- **NS-4 remediation:** scope bar Apply + structural pseudo-filters must be disabled or labeled deferred (`SettlementScopeBar.tsx`).

## Programme frontier

- **N-0008** NS-4 Settlement — independent review recorded; **gates_valid false**; awaits implementation fix + re-review
- **N-0010** Response — blocked on N-0008 programme-valid
- **N-0006** programme ledger sync deferred (frontier candidate; not started in N-0008 review)
- **N-0011** Steward — frontier

**Independent review evidence:** `.eif/audit/NS4_SETTLEMENT_20260902/independent-rendered-review.md`

**Env:** local Windows. Web `:3000` + API `:8001`.
