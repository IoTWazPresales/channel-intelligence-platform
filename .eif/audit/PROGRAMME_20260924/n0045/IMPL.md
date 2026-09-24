# N-0045 — D-d untracked files (run N0045_IMPL_20260924, 2026-09-24)

556 untracked paths at the start (`../n0045_untracked.txt`). Rule (Warren, D-d): archive outside the repo, never delete; commit only clearly real source, and list it.

## Committed (real project records)
| Commit | What | Why it is real |
|---|---|---|
| `2fe78bd5`, `e52494fc` and later ledger commits | 60 `.eif/runs/*/RUN_LOG.ndjson` | EIF run logs that the ledger's run provenance points at |
| `69864486` | `.eif/audit/**` (175 paths across past run folders), `.eif/runtime-probes/**` (59), `docs/verify/**` (20: session evidence docs + screenshots) | Evidence folders that ledger `evidence.path` entries and CURRENT/CONTEXT cite; pointers must resolve |
| `d4c5c102` | `.eif/CONTEXT.md`, `DECISIONS.md`, `DESIGN_EXPERIENCE_RECORD.md`, `JOURNEYS.yaml`, `RISK_REGISTER.md`, `OPPORTUNITY_REGISTER.md`, `MODULE_CONTRACT.md`, `MODEL_CAPABILITIES.md`, `MEMORY_PALACE.md`, `LESSONS.md`, `IMPLEMENTATION_BASELINE.md`, `HANDOFF.md`, `EMERGENCY_RECORD.md`, `DISCOVERY_REPORT.md`, `CONSULT.md`, `PROJECT_AUDIT_REPORT.md`, `programme-{migration,greenfield,brownfield}.md`, `.eif/.gitignore`, `.gitignore.eif.example` | The durable EIF artifacts CLAUDE.md names; they had never been committed (and are empty templates — finding) |

## To archive (Warren runs the script; the agent's guard denies paths outside the repo: FOREIGN_PATH)
`archive_untracked.ps1` (dry run by default, `-Apply` to move) moves the 105 paths in `archive_list.final.txt` to `C:\Users\warren_eliason\cip-untracked-archive-20260924\` preserving relative paths, skipping anything tracked. Contents: 94 `apps/api/.tmp_*` / `_*.py` / `_health_out.txt` / `ns2_programme_gates.py` scratch from past sessions, 8 `apps/api/scripts/ops` session probes (`_ns23_readonly_probe*.py`, `session_d_runtime_probe.py`, `session_verify_*.py`, `sleep4.py`, `.tmp_steward_queue_depth.py`) + `apps/api/tests/_setup_settle_smoke_db.py`, `apps/web/.tmp_n0026_vitest.txt`, `apps/docs/verify/**`, `docs/_preflight_probe.txt`, `docs/design/_evt_settlement_desk_resume.json`, `docs/design/gov008_payloads/_current.json`, `docs/memory/_preflight_0a.txt`, `docs/memory/part-c-preflight-20260919.md`, `replay_tmp.py/`.
Excluded on purpose: `apps/api/app/api/v1/endpoints/grid_fields.py`, `apps/api/app/services/grid_fields.py`, `apps/api/tests/test_grid_fields.py` (N-0034 work in flight).

## Left for Warren (EIF install / control plane — the agent may not stage or move these)
172 paths in `warren_controlplane_list.txt`: `.agents/skills/**` (132, installer copy of the skills), `.eif/runtime/**`, `.eif/runtime-events.jsonl`, `.eif/upgrade-history/**`, `.eif/upgrade-work/**`, `.eif/node-scope.lock`, `.eif/PROJECT_MANIFEST.md`, `.eif/ENVIRONMENT_POLICY.md`, five `AUTONOMY_POLICY` backups, `.cursor/rules/eif-*.mdc`, `.cursor-recovery/`. Decide per group: track, gitignore, or archive.

## Worktrees
`.wt-main-baseline/`, `.wt-bisect-5b55c81/`, `.wt-baseline-4ea1782/` are git worktrees — handled in N-0046 (BACKLOG-143).
