# CURRENT state

**Last updated:** 2026-09-05 (Units 2–4 evidence_basis)

**Branch:** `feat/ns-2-brief-nav-collapse`

**Last content pin:** `f8e1399`

**Alembic (code):** `20260905_0021` (fx_daily_rate + cpor_case proposed-rate columns)

**Alembic on cip:** `20260905_0021`

## On feat/ns-2-brief-nav-collapse

- **Product (Units 2–4):** `evidence_basis` is derived (not stored): claim_evidenced | source_attested | none. Surfaced and filterable on planner, case book, claims, workspace, settlement book mix, portfolio sibling `claim_evidenced_only`. Unmatched pending-report Case IDs stay on `cpor_payment_evidence` (nullable case_id, raw_source_row); Payments lens lists them; comparables rank attested file rows below CIP cases. Case-book ageing fills from window end when claim sale_date is absent (same outstanding total as the open book). N-0006 not started.
- **Product (Unit 1):** Booked FX lifecycle extends declared `roe_snapshot`. Daily USDZAR from Frankfurter (ECB); last-known fallback never blocks a case. Proposed rate is separate history; booking at approval does not overwrite it.
- **Product (Unit 0):** Promotions & Funding desktop dimensions migrated from design-lab source at 1280×800. Shared: `RAIL_WIDTH` 252 (`LabShell`), `WorkbenchCanvas` inset px 2.5 / pt 2 / pb 3, search `minWidth` 260.
- **I1–I5:** I1/I3/I4/I5 remain closed. **I2** still lab Market only (BACKLOG-164).
- **Programme:** PRG-20260831T145514; `frontier` is **only N-0006**. Do not start N-0006 (BACKLOG-170). Do not reopen N-0013 or D-0008.
- **D-0009 accepted:** Actions fold into Attention. Ledger still uncommitted.
- **D-0002** remains the open decision.
- **Next:** Unit 5 next D-0008 container (frontier is N-0006 only — do not start it).

**Programme frontier:** N-0006 only. Do not manufacture a path.

**Design language:** FROZEN v1.1 is **demoted**. Production funding follows the implemented design-lab React, including lab-specified dimensions.

**Deferred:** BACKLOG-164 I2-only. Budget ledger writer not chartered. Floating FX re-rate after approval is not implemented (mode exists; booked is the norm). CIP cases absent from the pending report (47) observed, not acted on.

**Env:** local Windows. Web `:3000` + API `:8001`.
