# Channel Intelligence Platform ? context router

Read [memory palace](docs/memory/MEMORY_PALACE.md), then [CURRENT](docs/memory/CURRENT.md). CURRENT is authoritative now; Git/running code are evidence. [AGENTS.md](AGENTS.md) and its required rules apply. Stop on unresolved conflicts; do not infer completion from a historical claim.

## Continuation and recovery

- [2026-11-23 handoff](docs/handoffs/2026-11-23/README.md): latest decisions, completion levels, proof limits and recovery instructions.
- [Map revision brief](docs/handoffs/2026-11-23/MAP_FEEDBACK.md): Warren's shipping-map parity/right-panel changes; old look not approved, provider unanswered.
- [Targets status](docs/handoffs/2026-11-23/TARGETS_STATUS.md): design/prototype only; requested module/theme not delivered.
- [ROADMAP](docs/ROADMAP.md), [BACKLOG](docs/BACKLOG.md), [commercial semantics](docs/COMMERCIAL_SEMANTICS.md).
- [Frozen prior CONTEXT](docs/memory/CONTEXT-archive-20261123-before-consolidation.md): all pre-consolidation router/changelog content retained unchanged; historical claims are not current state.

## Changelog ? newest first

- 2026-11-25 — Step 0 process rules: RULES, implementation log, recovery audit, reference PNGs, and CURRENT/BACKLOG corrections on `docs/impl-process-rules-20261125`. Docs commit `6ab1ce71`. 19 Nov audit merge `4a076379`. No product code. No live database write. Programme node `N-0120` is in the worktree ledger and was not in `6ab1ce71`.
- 2026-11-23 ? Consolidated portable handoff and preserved original drafts, seven separate branch refs, S3a/S4 patches and15untrackedfiles from three dirty worktrees. Bundle/archive/hashes/base patch checks passed; no product implementation/test rerun/deployment/DB change. Recorded map rejection/revisions as BACKLOG-268, design-only Targets/theme status as BACKLOG-269. CURRENT/ROADMAP updated; prior CONTEXT archived without loss. Checkpoint: `05d4f7e4`.
- 2026-11-22 ? Database map accepted live atc685bf63:291files/1818tests and independent seven-check live browser gate pass; clone layout persistence/isolation and exact cleanup proved with explicit transport/fixture limits. Web-only release and82.349s stability pass; previous failures retained.
- 2026-11-22 ? Inventory origin correction integrated2d374040, Line-up native double-toggle correction integrated7f2785d4 and verified live. Warren executed0064/65 migrations; separate read-only identity/schema/grant/count/backup checks pass. Earlier canonical stack deployment remains FAILED at busy-solo Celery ping; supplemental evidence is separate (BACKLOG-245).
- 2026-11-22 ? MapLibre browser-only preview used real proposals/temporary OpenFreeMap settings; production settings remained empty and prototype restored off. Latest feedback requires revisions; appearance/provider not approved. Location ambiguity retained in BACKLOG-267.

After significant work update CURRENT and append a concise changelog line here. Deferrals go in BACKLOG with TRIGGER. After a commit containing CURRENT, pin that commit hash on its changelog line. Never restore a large duplicate current-state/history dump in this router.
