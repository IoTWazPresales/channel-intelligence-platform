# Current state

**Last updated:** 2026-07-16 (DSI U4b — ASUS sellout row-19 sniff; re-soak)
**Verify git:** `git branch --show-current` · `git rev-parse --short HEAD`

---

## Branch and delivery

| Field | Value |
|-------|--------|
| **Branch** | `feat/dsi-unified-multifile` |
| **HEAD** | `8b46938` |
| **Alembic (DB)** | **`20260710_0072`** (unchanged) |
| **Consultant** | Opus U4 PASS; U4b real-file fix after soak miss |

---

## Shipped

- Unified multi-file + coverage + U0–U3 + U0e + U4 sniff
- **U4b** `SNIFF_ROWS=40` — ASUS weekly sellout header at row 19 (PINNACLE/MUSTEK); proven on Downloads files

---

## Next

- Restart API, re-preview the 14-file batch
- PR when soak passes
