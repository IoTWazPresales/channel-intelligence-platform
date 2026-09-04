# CURRENT state

**Last updated:** 2026-09-04 (independence overlay + BACKLOG-165 stdin + hooks.json restored)

**Branch:** `feat/ns-2-brief-nav-collapse`

**Last content pin:** `56aab49` (confirm with `git rev-parse` after any later commit)

**Alembic (code):** `20260902_0020` (N-0006 FX enforcement)

**Alembic on cip:** `20260902_0020`

## On feat/ns-2-brief-nav-collapse

- **Programme:** PRG-20260831T145514 rev **294**; `frontier` is **only N-0006**. N-0013 complete. N-0010/N-0011 **blocked** (BL-0001/BL-0002, D-0009 proposed — do not resolve). No other lawful frontier.
- **D-0008 accepted.** **D-0002** proposed. **D-0009** proposed. Do not resolve either. Do not reopen N-0013.
- **Independence overlay published** `2240f1a`: `independence.py` + actor/replay-aware engine/store; `program.py verify` ok rev 294, manifest hashes reconciled.
- **BACKLOG-165 CIP stdin slice done** `6111634`: watchdog armed before stdin read; complete JSON finishes without EOF; hung/incomplete stdin emits `HOOK_TIMEOUT` (prove: 2.347s / watchdog=2). Closed-stdin cases unchanged (allow / `ACTION_FORCE_VCS` / allow). `beforeReadFile` failClosed stays true.
- **hooks.json restored** from `.disabled` (blob identical to HEAD). Live Cursor deny this session: `CONTROL_PLANE_PROTECTED` on a shell command that named hook paths. `program.py --help` and `git rev-parse` run. No Cursor restart required for this proof.
- **Tests:** `@cip/web` **107 / 583 passed** with guard on after `testTimeout: 15000` (BACKLOG-162 closed).
- **BACKLOG-170 ACCEPTED:** N-0006 stays proposed; no synthetic `implementation_run`. Bookkeeping waits for BACKLOG-171 (EIF repair #1).

**Programme frontier:** none that is not N-0006. Stop. Do not manufacture a path. I1–I5 remain BACKLOG-164 (not programme nodes).

**Design language:** `docs/design/CIP_DESIGN_LANGUAGE.md` v1.1 is **under review**.

**Deferred hygiene:** BACKLOG-156 … 161, 164; BACKLOG-165 EIF-repo remainder; BACKLOG-166–169; BACKLOG-170 accepted/waiting EIF; **BACKLOG-171** EIF repair #1.

**Env:** local Windows. Web `:3000` + API `:8001`.
