# Current state

**Last updated:** 2026-07-16 (DSI U4 Opus PASS — re-soak 14-file batch)
**Verify git:** `git branch --show-current` · `git rev-parse --short HEAD`

---

## Branch and delivery

| Field | Value |
|-------|--------|
| **Branch** | `feat/dsi-unified-multifile` |
| **HEAD** | `1dc237d` |
| **Alembic (DB)** | **`20260710_0072`** (unchanged) |
| **Consultant** | Opus VERIFY **PASS** on U4 header sniff |

---

## Shipped

- Unified multi-file + coverage + U0–U3 + U0e
- **U4** corrective header-row sniff at load grain + `unmappable_reason` propose UX

---

## Next

- Human re-soak the 14-file batch (sellouts should get real signatures)
- PR when soak passes
