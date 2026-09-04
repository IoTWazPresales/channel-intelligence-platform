# CURRENT state

**Last updated:** 2026-09-04 (guard transport crash vs IDENTITY_TOOL)

**Branch:** `feat/ns-2-brief-nav-collapse`

**Last content pin:** `ea54b64` (confirm with `git rev-parse` after any later commit)

**Alembic (code):** `20260902_0020` (N-0006 FX enforcement)

**Alembic on cip:** `20260902_0020`

## On feat/ns-2-brief-nav-collapse

- **Programme:** PRG-20260831T145514 rev **294**; `frontier` is **only N-0006**. N-0013 complete. N-0010/N-0011 **blocked** (BL-0001/BL-0002, D-0009 proposed — do not resolve). No other lawful frontier.
- **D-0008 accepted.** **D-0002** proposed. **D-0009** proposed. Do not resolve either. Do not reopen N-0013. Do not start Promotions.
- **Independence overlay published** `2240f1a`: `independence.py` + actor/replay-aware engine/store; `program.py verify` ok rev 294, manifest hashes reconciled.
- **Guard transport crash (this session):** empty/truncated Cursor hook stdin is `HOOK_INPUT_INVALID` / `eif_guard_class=crash`, never `IDENTITY_TOOL`. Stdin retries 250ms after empty/incomplete. Read/Grep/Glob `preToolUse` skip git-identity (match `beforeReadFile`). CONSULT (opus CLI) `OBSERVATION_TRANSPORT: deny_crash`. `prove_stdin.py` PASS including zero-byte + mid-string truncate (Unterminated string col 49). Live policy deny: `CONTROL_PLANE_PROTECTED`. Burst after ts `1788527448`: zero `IDENTITY_TOOL` with `path:null`. Cursor Write on the guard is still `CONTROL_PLANE_PROTECTED`; repair applied via audit script.
- **BACKLOG-165 CIP stdin slice** `6111634` plus this transport classification. `beforeReadFile` failClosed stays true. BACKLOG-172: argv event-name before `allow_crash` is lawful.
- **hooks.json** remains restored. **Tests:** `@cip/web` **107 / 583 passed** (BACKLOG-162 closed).
- **BACKLOG-170 ACCEPTED:** N-0006 stays proposed; no synthetic `implementation_run`. Bookkeeping waits for BACKLOG-171 (EIF repair #1).

**Programme frontier:** none that is not N-0006. Stop. Do not manufacture a path. I1–I5 remain BACKLOG-164 (not programme nodes).

**Design language:** `docs/design/CIP_DESIGN_LANGUAGE.md` v1.1 is **under review**.

**Deferred hygiene:** BACKLOG-156 … 161, 164; BACKLOG-165 EIF-repo remainder; BACKLOG-166–169; BACKLOG-170 accepted/waiting EIF; **BACKLOG-171** EIF repair #1; **BACKLOG-172** launcher event identity.

**Env:** local Windows. Web `:3000` + API `:8001`.
