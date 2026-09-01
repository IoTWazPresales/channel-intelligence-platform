# CURRENT state

**Last updated:** 2026-09-01 (EIF host-runtime upgrade + N-0004 complete)

**Branch:** `feat/ns-2-brief-nav-collapse`

**Last content pin:** confirm HEAD with `git rev-parse` after commit

**Alembic (code):** `20260818_0019`

**Alembic on cip:** `20260818_0019`

## On feat/ns-2-brief-nav-collapse

- **EIF host runtime upgraded** to programme-host-execution repair (`9f74d9c`); host-local `python .eif/runtime/programme/program.py` operational.
- **Programme:** PRG-20260831T145514 rev 53; charter accepted; **N-0004 complete** (NS-2 Brief + six-container nav).
- **NS-2 shipped:** `/brief` grammar-3 landing, `WorkbenchSpine`, `GET /api/v1/brief/signals`, middleware redirects (`/`, `/dashboard` → `/brief`).
- **Baseline:** `46368f6` (BLN-0001) pre-NS-2 drawer shell.
- **Rendered verification:** `.eif/audit/NS2_RESUME_20260901/rendered-verification.md`

## Next (programme frontier)

- **N-0006** NS-1b FX mode (R3) — no N-0004 dependency
- **N-0007** NS-3 Stock (depends N-0004 ✓)
- **N-0009** NS-5 Lineup (depends N-0004 ✓)
- **N-0011** NS-7 Steward (depends N-0004 ✓)

**Env:** local Windows. Web `:3000` + API `:8001`.
