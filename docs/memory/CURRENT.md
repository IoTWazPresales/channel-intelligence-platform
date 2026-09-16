# CURRENT state

**Last updated:** 2026-09-16 (N-0028 Start work ActionCard strip)

**Branch:** `feat/ns-2-brief-nav-collapse`

**Last content pin:** `21d9182` (Start work ActionCard launch strip). Recon ledger pin: `2e8263d`. Payloads pin: `b6b0ac9`. Views pin: `5cc44c8`. Docs pin: `2812220`. Validate/lease ledger is recorded locally (programme snapshot 824) and still needs a host commit of the two programme-ledger files. Prior pins: BACKLOG-196 `aee82a7`; steward UX `4d9079b`.

**Alembic (code):** `20260906_0022` (`cpor_case.intelligence_exclude`)

**Alembic on cip:** `20260906_0022`

## On feat/ns-2-brief-nav-collapse

- **NS18 / N-0028 (committed `21d9182`):** Overview Start work is `StartWorkLaunch` + `ActionCard` (domain eyebrow, title, two-line explanation, START). Not PanelRow, not Import Center picker tiles, no Panel wrapper around the set. Desktop: full-width Start work, then dashboard `1fr` beside Needs attention `312px`. 390: Start work → Attention → dashboard. Steward-queue href stays `/admin/mappings`. N-0027 product behaviour, D-0002, N-0029 untouched.
- **Operator UX (committed `4d9079b`):** Steward queue opens the resolve workspace on the Steward leaf. Queue hides distributor/customer tokens with exactly one approved alias. `EnterpriseDataGrid` clips cell overflow.
- **BACKLOG-196:** payment-evidence-import reads `?code=` (trim only, exact Case ID). Overlay `GET …/overlay?code=` returns `focus_rows` via ORM equality on `external_case_code`. Does not mint `cpor_case`. No fuzzy match. Unit-tested. Live: unmatched `C19A50693` → import page shows 1 applied unlinked evidence row.
- **Programme:** PRG-20260831T145514. **N-0018–N-0026 complete.** **N-0027** and **N-0029** `in_progress` / `validate`; leases released. **N-0028** `in_progress` / `validate` / revision **44** / lease released (run `NS18_START_WORK_CARDS_20260916` / actor `gov-001`). Do not complete N-0028. Do not reopen N-0013. D-0002 remains open.
- **GOV-008 N-0025–N-0029** (vs impl NS13–NS17 / `gov-001`): N-0025 **VERIFIED_WITH_LIMITATIONS complete**. N-0026 **VERIFIED complete**. N-0027 and N-0029 **VERIFIED_WITH_LIMITATIONS** not complete. N-0028 Start work cards need a later independent GOV-008: click actual cards, prove route changes, prove role gating, verify desktop and 390px composition. Evidence still `.eif/audit/GOV008_N0025_N0029_20260915/independent-rendered-review.md` until that review.
- **D-0010 accepted** Option A: keep rail expansion. Rail and tabs are not one destination set.

**Mobile:** DIRECTION §6 desktop-primary with named 390px workflows. N-0025 Start work VERIFIED at 390×844 (above Attention). N-0028 390 composition is implemented; independent GOV-008 not recorded.

**Next:** Host commit of the validate/lease programme-ledger files if still uncommitted. Then independent GOV-008 of N-0028 — not in this implementation chat. Do not complete N-0028. Do not run GOV-008 in an implementation session.

**Design language:** Production follows implemented design-lab React. Do not cite a frozen design-language version or grammar number.

**Deferred:** BACKLOG-174–180. BACKLOG-181 token port done; IA settled D-0010 Option A. BACKLOG-182 Payments same-URL leftover. BACKLOG-183–186 N-0026 UNCOVERED. BACKLOG-187/188 N-0027. BACKLOG-189 lineup `?product=`. BACKLOG-190 lineup authoring workbench. BACKLOG-191 settlement workspace. BACKLOG-192 dual column pickers. BACKLOG-193 AG Grid Enterprise. BACKLOG-194 Lineup ApprovalBadge. BACKLOG-195 Import Center/Market chrome. BACKLOG-173. Budget ledger writer not chartered. Leftover `/market` stub. Stores master grid UNCOVERED. Cross-job steward accept/reject until Design Language v2. Pin-as-widget on Overview UNCOVERED. `/dashboard` legacy UNCOVERED.

**Env:** local Windows. Web `:3000` + API `:8001`. Sync/async engine on `cip` (`current_database()=cip`).
