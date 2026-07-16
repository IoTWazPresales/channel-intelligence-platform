# Current state

**Last updated:** 2026-07-16 (DSI U0–U3 completion after Fable CONSULT)
**Verify git:** `git branch --show-current` · `git rev-parse --short HEAD`

---

## Branch and delivery

| Field | Value |
|-------|--------|
| **Branch** | `feat/dsi-unified-multifile` |
| **Alembic (DB)** | **`20260710_0072`** (unchanged) |
| **Consultant** | Fable CONSULT READY — finish U0–U3 before soak |

---

## Shipped

- Unified multi-file batch + missed-week coverage
- **U0** pipeline multi-file/nested skip (fixes MultipleResultsFound + mapping wipe)
- **U1** per-sheet `column_samples` + hints in nested mapping state/UI
- **U2** cross-file raw-grain overlap FLAG
- **U3** file review strip + `POST …/dsi-file-exclusions`

---

## Next

- Browser soak using Fable acceptance checklist
- PR when soak passes
- Shell branch still separate unmerged track
