# Current state

**Last updated:** 2026-07-09 (CPOR U4.6 ? CST channel intelligence read-model)
**Verify git:** `git branch --show-current` · `git rev-parse --short HEAD`

---

## Branch and delivery

| Field | Value |
|-------|--------|
| **Branch** | `feat/cpor-unit-4-6-channel-intel` |
| **HEAD** | *(update after commit)* ? off U5 tip `a1b6e84` |
| **PR** | None open |
| **Alembic (code)** | `20260709_0068` (unchanged ? U4.6 no migration) |
| **Alembic (DB)** | **`20260709_0068`** on local `cip` |

---

## CPOR U4.6 ? DONE (CST channel intelligence read-model; no schema)

| Item | Status |
|------|--------|
| a) Read-model | `channel_intelligence/cst_read_model.py` ? vel 4/13wk, WoC, aged, trend |
| b) Explainability | factors + aged_factors; no composite score |
| c) API | `GET /api/v1/channel-intelligence` |
| d) Web | `/channel-intelligence` + nav under Channel Intelligence |
| e) Grain/sparse | monthly?weekly÷4.345; min 4 observed weeks ? insufficient_data |
| f) cip validation | SELECT-only: cst_rows=0 ? data_unavailable (by design) |
| g) Tests | 7 API unit; ALLOW unset |
| Schema | None |
| Next | STOP for Fable verify ? LC-U1 ? U6 ? BACKLOG-072 ? BACKLOG-061 |

---

## CPOR U5 ? DONE (settlement: claim import + consolidation + settle; no schema)

| Item | Status |
|------|--------|
| Feature | `a1b6e84` on `feat/cpor-unit-5-settlement` |
| Fable | PASS ? authored U4.6 |
| Next | U4.6 (this unit) |

---

## CPOR Batch 3 - DONE (TMP display-name-first shipping grid; no schema)

| Item | Status |
|------|--------|
| Feature | `ea62e66` / docs `4baf200` |
| Next | U5 (done) |
