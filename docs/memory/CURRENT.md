# Current state

**Last updated:** 2026-07-11 (BACKLOG-074 U3?U4g shipped; U4h skipped; next = lineup multi-folder + browser audit)
**Verify git:** `git branch --show-current` · `git rev-parse --short HEAD`

---

## Branch and delivery

| Field | Value |
|-------|--------|
| **Branch** | `feat/channel-ops-kpi-and-gap-scan-perf` |
| **HEAD** | see `git rev-parse --short HEAD` (U4g tip after push) |
| **PR** | Not opened |
| **Alembic (DB)** | **`20260710_0072`** on cip — no new migrations this program |

---

## BACKLOG-074 status (pushed)

| Unit | Status |
|------|--------|
| U3 + 3b CST chrome + pagination | PASS @ f9362f3 |
| U4 inventory doc | shipped with U3 |
| U4a CST slots + aliases | PASS @ b865070 |
| U4b inbound/evidence URL skip/limit | PASS @ 2eccb1c |
| U4c PMG skip/limit paging | shipped @ 9481479 |
| U4d CPOR case list paging | shipped @ 0c1775c |
| U4e PO gap + auto-link paging | shipped @ 8162d60 |
| U4f PVE exception paging | shipped (commit after this pin) |
| U4g Channel Ops sell-out/movements pager | shipped (commit after this pin) |
| U4h Channels & Regions | **skipped** — small catalog; already has toolbar+bulk |

**Shell swap:** still no (re-CONSULT reaffirmed).

---

## Next (different themes — prefer fresh chat)

1. **Lineup multi-folder historical upload** — plan viability + implement choose-folder multi-path parity with unified lineup importer.
2. **Read-only browser + DB audit** — visit each surface; compare numbers to source/DB; review only, no code changes.
3. Optional: Fable VERIFY batch for U4c–U4g; open PR for this branch.
4. Human soak: restart API; CST Key Accounts page past B; Channel Ops cards.

**Do not re-audit:** Theme B · BACKLOG-073 · shell-swap · U4 inventory ranking.
