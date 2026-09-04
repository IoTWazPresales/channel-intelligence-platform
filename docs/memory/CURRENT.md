# CURRENT state

**Last updated:** 2026-09-04 (vitest 583/583; BACKLOG-170 accepted; stdin patch INCOMPLETE)

**Branch:** `feat/ns-2-brief-nav-collapse`

**Last content pin:** `02df042` (confirm with `git rev-parse` after any later commit)

**Alembic (code):** `20260902_0020` (N-0006 FX enforcement)

**Alembic on cip:** `20260902_0020`

## On feat/ns-2-brief-nav-collapse

- **Programme:** PRG-20260831T145514 rev **294**; `frontier` is **only N-0006**. N-0013 complete. N-0010/N-0011 **blocked** (BL-0001/BL-0002, D-0009 proposed — do not resolve). No other lawful frontier.
- **D-0008 accepted.** **D-0002** proposed. **D-0009** proposed. Do not resolve either. Do not reopen N-0013.
- **Guard stdin patch INCOMPLETE:** operator chat-granted write to `.cursor/hooks/eif_guard.py`; hook still denied `CONTROL_PLANE_PROTECTED` (one failure, not retried). CONSULT keep_true: `beforeReadFile` failClosed untouched. Live deny this session: `CONTROL_PLANE_PROTECTED` on a shell command that named programme runtime paths.
- **Tests:** `@cip/web` **107 / 583 passed** with guard on after `testTimeout: 15000` (BACKLOG-162 closed).
- **BACKLOG-170 ACCEPTED:** N-0006 stays proposed; no synthetic `implementation_run`. Bookkeeping waits for BACKLOG-171 (EIF repair #1).
- **Dirty `.eif/runtime/programme/*`:** unpublished independence overlay vs HEAD (engine/store/manifest + untracked `independence.py`). CIP agent cannot `git add` that tree (`CONTROL_PLANE_PROTECTED`). Operator must stage or restore locally — do not carry blindly.

**Programme frontier:** none that is not N-0006. Stop. Do not manufacture a path. I1–I5 remain BACKLOG-164 (not programme nodes).

**Design language:** `docs/design/CIP_DESIGN_LANGUAGE.md` v1.1 is **under review**.

**Deferred hygiene:** BACKLOG-156 … 161, 164; BACKLOG-165 stdin remaining; BACKLOG-166–169; BACKLOG-170 accepted/waiting EIF; **BACKLOG-171** EIF repair #1.

**Env:** local Windows. Web `:3000` + API `:8001`.
