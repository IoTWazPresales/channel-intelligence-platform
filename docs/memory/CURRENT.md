# CURRENT state

**Last updated:** 2026-09-05 (CPOR pending-report Payments overlay)

**Branch:** `feat/ns-2-brief-nav-collapse`

**Last content pin:** `436db58`

**Alembic (code):** `20260902_0020` (N-0006 FX enforcement)

**Alembic on cip:** `20260902_0020`

## On feat/ns-2-brief-nav-collapse

- **Product (committed `436db58`):** Payments lens overlay for the ASUS CPOR pending report already on `cpor_payment_evidence` (job 977). Exact Case ID match (264/311), unmatched counts, 80 pending, Latest Comment from `raw_source_row`, USD vs ZAR paid honesty. Chrome **Import payment / CN** → payment-evidence-import. Not claim evidence; not budget ledger. **Do not re-audit Promotions & Funding against the lab — closed out.** Close-out remains `5e3eb5a`.
- **I1–I5:** I1/I3/I4/I5 remain closed. **I2** still lab Market only (BACKLOG-164).
- **Programme:** PRG-20260831T145514; `frontier` is **only N-0006**. Do not start N-0006 (BACKLOG-170). Do not reopen N-0013 or D-0008.
- **D-0009 accepted:** Actions fold into Attention; N-0010 is not a work container. Ledger (`.eif/program/PROGRAM.yaml` + `PROGRAM_LOG.ndjson` and generated views) still uncommitted — Warren unhooked git (control-plane protected for hooked agent).
- **D-0002** remains the open decision.
- **Next:** Warren commits D-0009 ledger (yaml/log, then generated views). Claim ageing / uplift stay blocked (no per-SKU claim lines). Do not write `fact_budget_*`. Do not start N-0006.

**Programme frontier:** N-0006 only. Do not manufacture a path.

**Design language:** FROZEN v1.1 is **demoted**. Production funding follows the implemented design-lab React, not CIP_DESIGN_LANGUAGE.md grammar containers.

**Deferred:** BACKLOG-164 now I2-only (Market mapping). Budget ledger writer not chartered.

**Env:** local Windows. Web `:3000` + API `:8001`.
