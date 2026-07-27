# CURRENT state

**Last updated:** 2026-07-27 (DSI mapping seamlessness clarity)
**Verify git:** `git branch --show-current` · `git rev-parse --short HEAD`

---

## Branch and delivery

| Field | Value |
|-------|--------|
| **Branch** | `feat/cpor-listing-status-audit` |
| **Alembic (DB)** | **`20260727_0074` on cip** |
| **HEAD** | uncommitted — DSI mapping seamlessness (post-merge `7f04c79`) |
| **Pushed?** | merge yes; clarity unit not committed |
| **Next** | Warren smoke weekly DSI batch (named layout blockers + Period N/A); then commit/push; then PR → main when ready. |

---

## DSI mapping seamlessness (clarity — implemented this session)

| Label | Fact |
|-------|------|
| **Banner** | Names failing layouts (`Layout N — needs …`); click jumps to that tab |
| **Progress** | `Layouts ready: N/M` in banner + multi-layout info alert |
| **Strip** | Sell-out files show **Period N/A** (invoice date on tabs); period actions only when SOH mapped without snapshot_date |
| **Gates** | Unchanged — stamps still ≠ sell-out txn date |
| **Out** | BACKLOG-078 exclude-sheet UI still deferred |
| **Tests** | `dsiStepUtils.test.ts` 21/21 |

---

## Merge note (2026-07-27)

Merged `feat/dsi-unified-multifile` (`2c2391e`) into this branch (base `618448c`).  
**Kept:** Unit F layout; CPOR + Units A–F; shipping KPIs.  
**Restored:** DSI multi-file batch/coverage/header sniff/file stamps.  
**BACKLOG remap:** multifile 074/075 → **077/078**.

---

## Shipping commercial KPIs (wired)

| Label | Fact |
|-------|------|
| **Contract** | `docs/SHIPPING_COMMERCIAL_KPI_CONTRACT.md` |
| **Phase 0 (cip)** | Gated current-incoming ~$63.4M; arriving qty hero |
| **BACKLOG** | **076** amount scale; **062** open+shipped pairs |

---

## Standing quality bar

**Contract or STOP · no half-PASS · code is evidence.**  
Steward contract **v1.6**. E1+E2 implemented, VERIFY deferred. A–D PASS; Unit F shipped.
