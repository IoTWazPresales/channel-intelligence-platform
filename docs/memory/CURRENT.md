# CURRENT state

**Last updated:** 2026-09-14 (N-0024 implementer validate; GOV-008 not recorded)

**Branch:** `feat/ns-2-brief-nav-collapse`

**Last content pin:** N-0024 product/docs commit this session — hash on CONTEXT after commit. Evidence `31a7155`; views `0d608de`.

**Last ledger pin:** `abaf04b` D-0010. Local programme snapshot **554**, run `NS12_NAV_DEST_20260913` / actor `gov-001`. `PROGRAM.yaml` / `PROGRAM_LOG.ndjson` remain dirty (`CONTROL_PLANE_PROTECTED` on `git add`).

**Alembic (code):** `20260906_0022` (`cpor_case.intelligence_exclude`)

**Alembic on cip:** `20260906_0022`

## On feat/ns-2-brief-nav-collapse

- **Programme:** PRG-20260831T145514. **N-0018–N-0022 complete.** N-0023 and N-0024 **in_progress** at **validate** (leases released). Do not reopen N-0013. D-0002 remains open. Do not complete N-0023 or N-0024 in an implementation run.
- **D-0010 accepted** Option A: keep rail expansion. Rail and tabs are not one destination set. No IA change in N-0024.
- **N-0024:** labelled controls open the job they name. Cover-breach → `/stock?lens=cover&status=under4w` with an Under 4w chip (union of under-2w + 2–4w). Failed-imports keeps “steward queue” and opens `/admin/mappings`. Inbound-open → `Open Supply · Shipments` at `/supply/shipments`. Rail/hub Lineup cases → `/lineup/cases`; Users & roles → `/admin/users/list`. Playwright VERIFIED those clicks. `soh_recon_not_run` not live this session (source only).
- **N-0023:** production `CapabilityRail` ports LabShell. Independent GOV-008 not recorded.
- **GOV-008 N-0019–N-0022:** still the last independent review (`docs/design/gov-008-n0019-n0022.md`).

**Mobile:** DIRECTION §6 desktop-primary with named 390px workflows. N-0024 is destination URLs, not a named 390 workflow.

**Next:** Independent GOV-008 on N-0024 (`gov-008` vs impl `NS12_NAV_DEST_20260913`) in a **new chat**. N-0023 GOV-008 still pending (`gov-008` vs `NS11_RAIL_20260913`). D-0002 when Warren chooses.

**Design language:** FROZEN v1.1 is **demoted**. Production follows implemented design-lab React. Do not cite a frozen design-language version or grammar number.

**Deferred:** BACKLOG-174–180. BACKLOG-181 token port done; IA settled D-0010 Option A. BACKLOG-173. Budget ledger writer not chartered. Leftover `/market` stub. Stores master grid UNCOVERED. Cross-job steward accept/reject until Design Language v2. Pin-as-widget on Overview UNCOVERED. `/dashboard` legacy UNCOVERED.

**Env:** local Windows. Web `:3000` + API `:8001`. Sync/async engine on `cip` (`current_database()=cip`). Brief href changes need API process restart (uvicorn `--reload` missed `brief_signals.py` once this session).
