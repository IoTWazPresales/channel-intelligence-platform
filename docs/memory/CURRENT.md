# CURRENT state

**Last updated:** 2026-09-04 (E stdin-hang VERIFIED, hook write blocked; F vitest 107 collected; G N-0006 STOP / BACKLOG-170)

**Branch:** `feat/ns-2-brief-nav-collapse`

**Last content pin:** `e728508` (confirm with `git rev-parse` after any later commit)

**Alembic (code):** `20260902_0020` (N-0006 FX enforcement)

**Alembic on cip:** `20260902_0020`

## On feat/ns-2-brief-nav-collapse

- **Programme:** PRG-20260831T145514 rev **294**; `verify` **ok**. N-0013 **complete** (node rev 105). Frontier: **N-0006** only — **not advanced** (BACKLOG-170).
- **D-0008 accepted** (r3.1 capability-domain IA). **D-0002** remains **proposed**. **D-0009** remains **proposed**. Do not resolve either. Do not reopen N-0013.
- **Guard (2026-09-04 E):** Observation path still cheap. Shell stdin-to-EOF **hangs if the pipe stays open**: watchdog arms after `os.read` EOF, so a hung read emits nothing (`prove_stdin.py` hung-open 12.048s, empty stdout, no `HOOK_TIMEOUT`). Closed-pipe allow **1.006s**; `ACTION_FORCE_VCS` deny **0.941s**; identity ≈ **0.57s** (not a 10s class). Live `program.py --help` ran. **Fix not landed:** `CONTROL_PLANE_PROTECTED` on `.cursor/hooks/eif_guard.py` (one deny, not retried). CONSULT keep_true on `beforeReadFile` failClosed. `PROGRAMME_GIT_STAGE` is not a reason code.
- **Tests:** `@cip/web` guard-on **107 files collected**, 582 passed + 1 full-suite 5s timeout (`DsiCandidateStewardPanel` resolve-product); isolation 2/2 in 1.88s (BACKLOG-162). Prior 104/461 uncollected **not reproduced**. Guard-off suite not run (would require hooks.json control-plane write).
- **Implementation ACs I1–I5** remain design-lab capability work, not this slice.
- **Production D-0008 shell** shipped in `41a8c4b`.

## Programme frontier

- **N-0006** — parked at BACKLOG-170 until Warren accepts a disclosed post-hoc `implementation_run` or an EIF-repo pre-existing-implementation event. Product already ships `fx_mode` / `fx_settle_allowed`.
- Next product work: capability implementation slices (I1–I5), or operator grant to edit `.cursor/hooks/**` (BACKLOG-165 remaining).

**Design language:** `docs/design/CIP_DESIGN_LANGUAGE.md` v1.1 is **under review**; do not treat as quality ceiling.

**Deferred hygiene:** BACKLOG-156 … BACKLOG-162, 164; BACKLOG-165 CIP stdin hang remaining; BACKLOG-166–169; **BACKLOG-170** (N-0006 complete invariant).

**Env:** local Windows. Web `:3000` + API `:8001`.
