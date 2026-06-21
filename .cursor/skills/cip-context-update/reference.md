# CURRENT.md update — example

Replace sections in `docs/memory/CURRENT.md` — do not append duplicate blocks.

```markdown
## Branch and delivery

| Field | Value |
|-------|--------|
| **Branch** | `fix/shipment-steward-performance` |
| **HEAD (snapshot)** | `abc1234` — short subject |
| **Alembic (code)** | `20260609_0049` — confirm with `alembic current` |

## What is working

- Shipped item one line

## In progress / not proven live

- Unproven live: needs worker restart + job soak

## Next (recommended)

1. Restart API + worker; soak job #N.
```

## CONTEXT.md changelog row

```markdown
| 2026-06-13 | `abc1234` — short summary of session outcome |
```

## Common mistakes

| Mistake | Fix |
|---------|-----|
| Added CURRENT STATE block to CONTEXT.md | Use CURRENT.md + changelog row only |
| Deleted CONTEXT archive | Never edit archive files |
| Claimed "fixed" without soak | Use wired + unit-tested / unproven live |
| Deferral only in chat | Add BACKLOG.md entry with TRIGGER |
