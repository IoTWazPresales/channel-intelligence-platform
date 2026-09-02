# CURRENT state

**Last updated:** 2026-09-02 (N-0013 architecture approval gate — operator decision required)

**Branch:** `feat/ns-2-brief-nav-collapse`

**Last content pin:** confirm HEAD with `git rev-parse` after commit

**Alembic (code):** `20260902_0020` (N-0006 FX enforcement)

**Alembic on cip:** `20260902_0020`

## On feat/ns-2-brief-nav-collapse

- **Programme:** PRG-20260831T145514 rev **199**; `verify` **ok** (no issues).
- **Charter amended** — full-platform UI/UX redesign; design language = quality benchmark only; Reports/Admin now in scope; construction blocked until N-0013 operator acceptance.
- **N-0013** **`ready`** — full-platform IA architecture approval package; operator acceptance **pending**; decision **D-0001** proposed.
- **N-0010** **`blocked`** — re-titled NS-6 Actions container; depends N-0013.
- **N-0011** **`blocked`** — re-titled NS-7 Data container; depends N-0013.
- **N-0004**, **N-0007**, **N-0008**, **N-0009**, **N-0012** complete (preserved; convergence waves follow approval).
- **N-0006** programme ledger still **`proposed`** — product shipped; Warren hygiene decision on backfill.

## Programme frontier

- **N-0013** — **operator approval required** (architecture/UI/language package)
- **N-0006** — FX ledger hygiene (not architecture-blocked)

**Blocked until N-0013 accepted:** N-0010, N-0011, all post-approval shell/primitive/migration work.

**Approval package:** `docs/design/CIP_PLATFORM_ARCHITECTURE_PROPOSAL.md` · rendered evidence `.eif/audit/NS_RECONCILE_20260902/` · independent review PASS (`independent-rendered-review.md`).

**Reconciliation evidence:** `docs/design/CIP_FULL_PLATFORM_RECONCILIATION.md` (50 capabilities; 0 RETIRE).

**Deferred hygiene:** BACKLOG-156; BACKLOG-157.

**Env:** local Windows. Web `:3000` + API `:8001`.
