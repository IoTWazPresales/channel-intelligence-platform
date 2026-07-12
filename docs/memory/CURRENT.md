# Current state

**Last updated:** 2026-07-12 (ops shell + column catalogs + CST key-account bulk)
**Verify git:** `git branch --show-current` · `git rev-parse --short HEAD`

---

## Branch and delivery

| Field | Value |
|-------|--------|
| **Branch** | `feat/ops-master-grid-shell-parity` |
| **Alembic (DB)** | **`20260710_0072`** (unchanged) |
| **Consultant default** | **Opus** (`docs/WORKFLOW_DUAL_AGENT.md`) — Fable optional |

---

## Exclusions (still)

- Channel Ops **Overview** (charts only)
- Import **`ImportStewardCandidateWorkspace`**

---

## VERIFY queue (Opus default)

Use audit `.tmp/OPS_MASTER_GRID_SHELL_AUDIT.md`. Queue:

1. **Shell adoption** — shipping, Channel Ops data tabs, CST tabs, PVE exceptions on `MasterDataGridShell`
2. **Column catalogs** — shipping optionals in shell Columns; Channel Ops / CST / PVE richer groups + default-hidden fields
3. **CST key-account bulk** — `POST …/key-accounts/batch-patch` + UI (key on/off, strategic tier, reports expected)
4. **Sell-out product catalogue Columns** — `specs_flat` / `specs_field_keys` + discovered catalogue specs in picker (Products parity); specs default-hidden

**Follow-on (not this branch slice):** CPOR / PM gaps / PO / shipment evidence; PVE drill shell.

---

## What works (this branch)

| Surface | Shell | Columns depth | Bulk |
|---------|-------|---------------|------|
| `/shipping` | Yes | Core + Additional (API optionals) | No |
| Channel Ops Sell-out / Inventory / Movements | Yes | Split groups + default-hidden | No |
| CST key-accounts | Yes | + partner_tier / threshold / notes | **Yes** (batch-patch) |
| CST slots | Yes | Slot fields | No |
| CST aliases | Yes | Alias/Product | Confirm/Reject batch |
| PVE exceptions | Yes | Entity/Units/Value | No |

---

## Next

1. Commit/push if not yet (Cursor) ? Opus VERIFY on queue items 1–3
2. Browser soak: Columns picker + CST bulk selecting mode
