# CURRENT state

**Last updated:** 2026-09-05 (Promotions & Funding close-out committed)

**Branch:** `feat/ns-2-brief-nav-collapse`

**Last content pin:** `5e3eb5a`

**Alembic (code):** `20260902_0020` (N-0006 FX enforcement)

**Alembic on cip:** `20260902_0020`

## On feat/ns-2-brief-nav-collapse

- **Product (committed `5e3eb5a`):** Promotions & Funding close-out against the design lab. Case book lives in `CaseBookSurface` (mounted from `/commercial-planner/cpor-cases`). Domain chrome on remaining lenses; settlement book read model + tests. **Do not re-audit Promotions & Funding against the lab — closed out.**
- **I1–I5:** I1/I3/I4/I5 remain closed. **I2** still lab Market only (BACKLOG-164).
- **Programme:** PRG-20260831T145514; `frontier` is **only N-0006**. Do not start N-0006 (BACKLOG-170). Do not reopen N-0013 or D-0008.
- **D-0009 accepted:** Actions fold into Attention; N-0010 is not a work container. Ledger (`.eif/program/PROGRAM.yaml` + `PROGRAM_LOG.ndjson` and generated views) still uncommitted at this pin — next commit on this branch.
- **D-0002** remains the open decision.
- **Next:** commit + push D-0009 ledger (yaml/log, then generated views), then UNIT 2 CPOR pending-report import workflow + load. Claim ageing / uplift stay blocked (no per-SKU claim lines). Do not write `fact_budget_*`.

**Programme frontier:** N-0006 only. Do not manufacture a path.

**Design language:** FROZEN v1.1 is **demoted**. Production funding follows the implemented design-lab React, not CIP_DESIGN_LANGUAGE.md grammar containers.

**Deferred:** BACKLOG-164 now I2-only (Market mapping). Budget ledger writer not chartered.

**Env:** local Windows. Web `:3000` + API `:8001`.
