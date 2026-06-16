# CONTEXT.md update — example top block

```markdown
## CURRENT STATE — Jun 13, 2026 (example feature) — supersedes every block below

- **Branch:** `fix/shipment-steward-performance` @ `abc1234` (pushed)
- **Goal:** Short description of what this session accomplished.
- **Shipped:**
  - Module/file: what changed in one line each
- **Tests:** `pytest apps/api/tests/test_foo.py` — 12 pass; no cip writes
- **Proven vs unproven:**
  - Wired + unit-tested: new guard in `imports.py`
  - Unproven live: needs worker restart + job #43 soak
- **Next:** Restart API + worker; re-validate job #43.
- **Alembic:** unchanged at `20260607_0047` on cip
```

## Insertion anchor (exact pattern)

Find:

```markdown
# Channel Intelligence Platform — Current Context

## CURRENT STATE —
```

Replace with new block + preserved old first line of previous state.

## Common mistakes

| Mistake | Fix |
|---------|-----|
| Deleted old CURRENT STATE sections | Restore from git; only insert at top |
| Rewrote middle of file | Revert; insert-only |
| "Fixed" without soak | Use wired + unit-tested / unproven live |
| Backlog item only in chat | Add to `docs/BACKLOG.md` with TRIGGER |
