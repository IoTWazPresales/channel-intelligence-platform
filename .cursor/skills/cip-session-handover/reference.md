# Session handover — reference

## Example handover (good)

```markdown
## Session handover

**Branch:** `fix/shipment-steward-performance` @ `ec3842e` — 0 ahead, in sync with origin

**Current focus:** DSI validate idle-in-tx backstop shipped; job #43 soak needed to prove live.

**Proven vs unproven:**
- Proven: sub-phase heartbeats, per-chunk validate commits (job #43 ~53 min / 168k rows)
- Wired but unproven: idle_in_transaction_session_timeout backstop, dispatch guard when Celery state lost

**Alembic:** code head `20260608_0048` — migration created, not applied to cip/Supabase

**Recommended next step:** Restart API + worker, re-validate job #43, monitor `dsi_validate_sub_phase` + `pg_stat_activity`.

**Blockers:** P1 ops restart required before soak proves P0 backstop.
```

## Example handover (dirty tree)

```markdown
## Session handover

**Branch:** `fix/shipment-steward-performance` @ `7fe2581` — **2 commits ahead, not pushed**

**Working tree:** dirty — modified `distributor_sales_inventory.py`, untracked `apps/api/scripts/_*.py` (diag scripts; do not commit)

**Current focus:** …

**Recommended next step:** Push commits before switching to cloud, or stash intentionally.
```

## CONTEXT.md top-block anatomy

A healthy top block usually contains:

- **Branch** and commit hash
- **Incident or feature** in one line
- **What shipped** (bullet list)
- **Tests** run and pass/fail
- **Next** — explicit single action
- **Proven vs unproven** language where relevant

Older blocks are historical — the line "supersedes every block below" is literal.

## Backlog triage (when user asks "outstanding tasks")

1. Read `docs/BACKLOG.md` table of contents / entry IDs
2. For each entry, check TRIGGER against current CONTEXT
3. Classify: **done** (close or note in CONTEXT), **trigger fired** (candidate next work), **still parked**
4. Do not implement backlog items without summarising "what changes what" and user approval

## Cloud ↔ local checklist (abbreviated)

**Leaving:**
1. `git status` → clean or intentional
2. `git fetch origin`
3. Push if `origin/branch..HEAD` non-empty
4. Tell other environment: branch + hash + "pull before starting"

**Arriving:**
1. `git fetch origin`
2. Checkout same branch, `git pull` if behind
3. Read CONTEXT top block
4. This handover skill

## Related skills (project)

Full list: **`Run cip-skills-index`**

| Invoke | When |
|--------|------|
| `Run cip-fix-protocol-audit` | Importer bug/perf — path map before code |
| `Run cip-read-only-audit` | Report only, verify hypothesis |
| `Run cip-context-update` | End of session — insert-only CONTEXT |
| `Run cip-git-handoff` | Local ↔ cloud sync |
