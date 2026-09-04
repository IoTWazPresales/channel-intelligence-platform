# CURRENT state

**Last updated:** 2026-09-04 (CIP guard repair; CONSULT keep_true on beforeReadFile failClosed)

**Branch:** `feat/ns-2-brief-nav-collapse`

**Last content pin:** confirm HEAD with `git rev-parse` after commit

**Alembic (code):** `20260902_0020` (N-0006 FX enforcement)

**Alembic on cip:** `20260902_0020`

## On feat/ns-2-brief-nav-collapse

- **Programme:** PRG-20260831T145514 rev **294**; `verify` **ok**. N-0013 **complete** (node rev 105). Frontier: **N-0006** only.
- **D-0008 accepted** (r3.1 capability-domain IA). **D-0002** remains **proposed**. **D-0009** remains **proposed**. Do not resolve either. Do not reopen N-0013.
- **Guard repair (2026-09-04):** stdin read-to-EOF; skip git-identity on observation hooks; cache/dedupe same-repo `repository_anchors`; `eif_guard_class` crash vs policy (`EIF_GUARD_CRASH:` / `EIF_GUARD_POLICY:`). `hooks.json` restored. CONSULT (opus CLI): `FAILCLOSED_BEFORE_READ: keep_true` — fail-open would weaken SENSITIVE_READ / SECRET_IN_READ / FOREIGN_READ / OUT_OF_OBSERVATION_SCOPE on hook crash. `PROGRAMME_GIT_STAGE` is not a reason code in this tree. Proof denials: `ACTION_FORCE_VCS`, `SENSITIVE_READ`, `FOREIGN_READ`. BACKLOG-163/165 CIP slices done; EIF-repo remainder of 165 still parked.
- **CONSULT provenance (GOV-008 addendum, 2026-09-04):** `consult_model_logged` is **VERIFIED** from Claude Code CLI session jsonl (`claude-opus-4-8`, `entrypoint=sdk-cli`, `promptSource=sdk`, Claude Code 2.1.202, `stop_reason=end_turn`): `ce2fbf92-…` (IA, 2026-09-02T16:49:43Z) and `46068c16-…` (commercial, 21:34:04Z) under `~/.claude/projects/C--Users-warren-eliason-channel-intelligence-platform/`. Verdicts unchanged. N-0013 not reopened. Seq 287 in `PROGRAM_LOG.ndjson` remains `UNVERIFIED` (append-only; no engine event for post-hoc caveat resolution — BACKLOG-169). Session logs live outside the repo and are not durable long-term.
- **Implementation ACs I1–I5** remain design-lab capability work, not this shell slice.
- **Production D-0008 shell** shipped in `41a8c4b`.
- **Tests:** `@cip/web` vitest last green **107 files / 583 passed** (re-run as guard-on proof in this session). `pnpm typecheck` still fails on **pre-existing** errors — not introduced by this slice.

## Programme frontier

- **N-0006** — FX ledger hygiene.
- Next product work: capability implementation slices (I1–I5) or N-0006. Do not opportunistically retouch design-lab fixtures.

**Design language:** `docs/design/CIP_DESIGN_LANGUAGE.md` v1.1 is **under review**; do not treat as quality ceiling.

**Deferred hygiene:** BACKLOG-156 … BACKLOG-162, 164; BACKLOG-165 EIF-repo remainder; BACKLOG-166 (CONSULT invocation record); BACKLOG-167 (seed/response transcription vs capture); BACKLOG-168 (AI resolver missing `ANTHROPIC_API_KEY` must fail loudly); BACKLOG-169 (engine cannot record post-hoc caveat resolution).

**Env:** local Windows. Web `:3000` + API `:8001`.
