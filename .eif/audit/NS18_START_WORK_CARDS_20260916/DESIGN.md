# N-0028 design record — Start work action cards

**Run:** `NS18_START_WORK_CARDS_20260916`  
**provenance:** design-direction  
**Node stays at validate.** Independent GOV-008 is a later session.

---

## What was wrong

**Panel / PanelRow (live before this correction).** Start work used the same analytical blotter as Needs attention: `Panel` + `PanelRow`, left hairline, truncated secondary. It read as a settings/menu list. Severity language (left bar) is for exceptions, not jobs.

**Previous outlined cards (`a969d63`).** MUI `Card outlined` + `CardActionArea` cloned from Import Center type-pickers (label + technical slug inside a “Start an import” Panel). On Overview those tiles were equal-weight generic boxes with long copy and no go-affordance. Operator: they looked poor. Restoring that file is not the design.

**Wider Overview.** N-0025 put Start work in the intelligence column, so the dashboard sat below the fold. That is a composition problem, not only a card-skin problem.

---

## Directions (diverged, then converged)

| | A — Launch strip then intelligence | B — Cards in the left column |
|---|---|---|
| Philosophy | Jobs are a launch pad; exceptions and KPIs keep N-0019’s two-column body | Keep N-0025 page grid; only replace rows with tiles |
| Layout | Full-width action-card strip, then dashboard `1fr` ∥ attention `312px` | Start cards left, attention right, dashboard below |
| Hierarchy | Title / 2-line explanation / START → on each tile; blotter rows stay on Attention | Same tiles, but they compete with Attention as two stacks |
| Fold (admin, 7 cards) | Two compact rows (~180px); dashboard still in the first viewport | Seven tiles in a 2-col left stack; dashboard recedes |
| Rendered | Lab `/design-lab` admin: 4+3 cards, charts still visible | Lab `?compose=column` a11y order: Start work → Needs attention → dashboard |

**Winner: A.** B still pushes intelligence down and makes Start work look like a second blotter column. A keeps N-0025 “Start work prime” and restores N-0019’s dashboard ∥ attention body.

`?compose=column` was removed after the comparison so the lab referent is a single composition.

---

## Design signatures

1. **Jobs are tiles; exceptions are rows.** ActionCard hairline + cyan hover. PanelRow left-bar stays on Needs attention only.
2. **Start work is a launch strip**, not a wrapper Panel around cards.
3. **Cyan means go** (START →). Severity colour stays on the blotter.
4. **Eyebrows name the domain** (Plan / Data / Funding) so seven admin cards scan as distinct jobs, not a menu.

Identity tokens: Inter 13px/600 titles, 12px secondary 2-line clamp, 10px caps eyebrows, 11px caps START, radius 1.5, divider hairline, primary hover fill 6% alpha. No nested Paper. No Import Center slugs.

---

## Lab referent

`apps/web/src/design-lab/surfaces/OverviewSurface.tsx` mounts `StartWorkLaunch` (strip) above the dashboard ∥ attention grid. Lab hrefs stay inside `/design-lab/*`. Role gating uses the same `startVerbsForRole` catalog as production.

Production `OverviewHub` consumes the same `StartWorkLaunch` with production hrefs.

---

## Comparison vs production-before

| | Before (PanelRow) | After (lab A → production) |
|---|---|---|
| Start work chrome | Panel + rows | Typography heading + action cards |
| 7 admin jobs | Vertical list | 4+3 card grid |
| Dashboard | Below two lists | Beside Attention, under the strip |
| Import Center | Unrelated picker tiles | Unchanged; not the Overview pattern |
