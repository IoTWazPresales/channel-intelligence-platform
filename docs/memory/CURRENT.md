# CURRENT state

**Last updated:** 2026-09-04 (Promotions & Funding fidelity + number coherence)

**Branch:** `feat/ns-2-brief-nav-collapse`

**Last content pin:** `4fd05c4`

**Alembic (code):** `20260902_0020` (N-0006 FX enforcement)

**Alembic on cip:** `20260902_0020`

## On feat/ns-2-brief-nav-collapse

- **Product (this session):** Domain chrome restored on all Promotions & Funding lenses (H1 **Promotions & Funding**, description, live subtitle, three actions). Nav labels no longer truncate (`RAIL_WIDTH` 296). Tenant chip is seed (`Default tenant` / `26Q3`) — not Aurora / FY26. Number-coherence: labels + one mixed-denominator fix; numbers not reconciled across surfaces. Needs a decision grouped/ranked. Remaining lenses (claims cards at 390, payments honesty, plan templates surface, terms copy) migrated without fixture data. Budget ledger stays a lens tab only. Template-driven export not built — Partly built / Planned markers carried.
- **I1–I5:** I1/I3/I4/I5 remain closed. **I2** still lab Market only (BACKLOG-164).
- **Programme:** PRG-20260831T145514 rev **295**; `frontier` is **only N-0006**. Do not start N-0006. Do not reopen N-0013, D-0008, D-0009. D-0009 ledger (`.eif/`) still uncommitted — leave it.
- **D-0009 accepted:** Actions fold into Attention; N-0010 is not a work container. **D-0002** remains the open decision.
- **Tests:** `@cip/web` **112 / 592 passed** (`testTimeout: 15000`). API `test_brief_signals.py` + `test_cpor_support_bias.py` 4 passed (no cip writes).
- **Ops:** local web `:3000` + API `:8001` were up for browser verification.

**Programme frontier:** N-0006 only. Do not manufacture a path.

**Design language:** FROZEN v1.1 is **demoted**. Production funding follows the implemented design-lab React, not CIP_DESIGN_LANGUAGE.md grammar containers.

**Findings (not invented):** no AM vs Ken permission split on CPOR API; listing/competitor/cover not joined on `cpor_case_line`; B4 propose still needs a seed case id; no `proposed→draft`; template-driven export not built; `blocked_amount` ≈ R1,050 above `book_total` (CONSULT side note, not this slice).

**Deferred:** BACKLOG-164 now I2-only (Market mapping). Duplicate Price History / product-scoped listing headlines are Market, not this slice. Budget ledger writer not chartered.

**Env:** local Windows. Web `:3000` + API `:8001`.
