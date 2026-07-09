# Current state

**Last updated:** 2026-07-09 (LC-U1 ? Listing Capture v0; migration authored NOT applied)
**Verify git:** `git branch --show-current` · `git rev-parse --short HEAD`

---

## Branch and delivery

| Field | Value |
|-------|--------|
| **Branch** | `feat/lc-unit-1-listing-capture` |
| **HEAD** | *(update after commit)* ? off U4.6 tip `c593677` |
| **PR** | None open |
| **Alembic (code)** | `20260709_0069` (head) ? listing tables |
| **Alembic (DB)** | **`20260709_0068`** on local `cip` ? **0069 NOT applied** (awaits Warren) |

---

## LC-U1 ? DONE (code); migration pending on cip

| Item | Status |
|------|--------|
| a) Migration | `20260709_0069` authored ? customer_listing + listing_observation |
| b) Registry API | `/api/v1/listing-capture` CRUD + CSV + status |
| c) Proposals | confirm/reject from `cst_listing_seed` (steward only) |
| d) Observation | compress/parse/reparse; mocked HTTP; dead-link backoff |
| e) Beat | `listing_capture.poll_listings` gated no-op (default disabled) |
| f) Web | `/listing-capture` + nav |
| g) Tests | 10 passed; ALLOW unset; no live HTTP |
| cip | SELECT-only: tables absent; alembic still 0068 |
| **STOP** | Warren must approve `alembic upgrade` to apply 0069 on cip |

---

## CPOR U4.6 ? DONE (`c593677`)

CST channel intelligence read-model; Fable PASS ? LC-U1.

---

## CPOR U5 ? DONE (`a1b6e84`)

Settlement claim import + consolidation.

---

## Next after LC-U1 Fable verify

U6 ? BACKLOG-072 ? BACKLOG-061
