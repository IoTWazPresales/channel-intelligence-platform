# CURRENT state

**Last updated:** 2026-09-02 (N-0008 Settlement implementation)

**Branch:** `feat/ns-2-brief-nav-collapse`

**Last content pin:** confirm HEAD with `git rev-parse` after commit

**Alembic (code):** `20260902_0020` (N-0006 FX enforcement)

**Alembic on cip:** `20260902_0020`

## On feat/ns-2-brief-nav-collapse

- **Programme:** PRG-20260831T145514 rev 131; **N-0008** `in_progress` @ verify (implementation run `NS4_SETTLEMENT_IMPL_20260902`); **N-0004**, **N-0007**, **N-0009**, **N-0012** complete; **N-0006** complete in product (`92f8edb`) but programme ledger still `proposed`.
- **NS-4 shipped (uncommitted/pending push):** Settlement scope bar, full case pane via `CporCaseWorkspace`, settle preview dialog, portfolio read fold, regime warm-start fix.
- **Rendered verification:** `.eif/audit/NS4_SETTLEMENT_20260902/rendered-verification.md`

## Programme frontier

- **N-0008** NS-4 Settlement — `in_progress` @ verify; awaits independent GOV-008 review (not PASS in impl session)
- **N-0010** Response — blocked on N-0008 programme-valid
- **N-0006** programme ledger sync deferred

**Env:** local Windows. Web `:3000` + API `:8001`.
