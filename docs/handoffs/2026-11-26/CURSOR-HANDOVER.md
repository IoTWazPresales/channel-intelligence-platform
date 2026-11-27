# Handover to Cursor: CIP recovery, state at 26 Nov 2026 evening

Written by the Claude coordinator (Sonnet) because Claude usage is nearly spent. Warren's words: "Then I think we can switch back to cursor and use you for heavy edits, and reviews." Read this first, then `docs/handoffs/2026-11-24/briefs/` and the per-step trackers in `docs/handoffs/2026-11-24/steps/`.

## Standing rules (Warren's words win; nothing here overrides them)
- Merge to `feat/integrate-20261103` only, never main. Commit means push. Stage explicit paths only.
- No hardcoding; reuse shared components. Products show `dim_product.sales_model_name`.
- Promotions are sell-through. The planner shows customer promotions, never sell-out, and never closed, settled or ended cases by default.
- Live `cip` is read-only except Warren-approved writes. Tests run only on `cip_test`. Never print secrets or DB URLs.
- Never remove a screen. Never rewrite tests to make them pass.
- Quote Warren; never invent a "Decision:"; label every ASSUMPTION; ask plain questions.
- Visual gate: render the live page and the mockups (Playwright, dark and light), compare, report in text.
- The main checkout is the live deploy checkout: never edit, switch, stash, reset or clean it. Work in `.worktrees\`. Back up before every live restart. Deploy with `scripts\cip-deploy.ps1` (plan first, then `-Execute`).
- Backup: `scripts\ops\backup_cip.ps1` prints the DB URL, so do not use it as is. The `cip` role is not a superuser and forced RLS is on 53 tables. A working read-only dump is `pg_dump -Fc --enable-row-security` with `PGOPTIONS="-c cip.product_lines=*"`, launched from a script that never prints the URL (see `.tmp/backup_quiet.py`, untracked).

## Step status
| Step | Branch | State |
|---|---|---|
| 0 docs/process | `docs/impl-process-rules-20261125` | Committed. Ledger N-0120 done by Warren. |
| 1 Monitored listings matrix (N-0121) | `fix/listings-matrix-centrepiece-20261125` @ `09415710` | Built, reviewed twice (Sonnet, Opus), merged into integrate at `f4feb367`. Live proof: see the section below. |
| 4a theme quick fixes + nav rail (N-0124) | `fix/theme-titles-background-20261125` @ `2ecec103` | Built, reviewed (Opus x2), merged at `f4feb367`. Live proof: see below. |
| 4b theme through shared components (N-0125+) | not started | Next. Slices S1-S3 touch only theme files. |
| 2 planner calendar (N-0122) | `fix/planner-sellthrough-calendar-20261125` @ `cba724cc`, worktree `.worktrees/impl-step2` | API + cip_test tests and web scope/History toggle/mockup timeline are pushed. No hand-back and no finished visual gate. Use Opus (medium) to finish. Brief: `briefs/step2.md`. |
| 3 discovery engine (N-0123) | `feat/discovery-autodiscover-20261125`, worktree `.worktrees/impl-step3` | Uncommitted work in autoconfig, listing_discovery, celery_app, tasks, `autoconfig_schedule.py`, `prove_discovery_libraries.py`. Brief: `briefs/step3.md`. Review the diff before committing. |
| 5 clean-up | - | Last. Give Warren a list of branches/worktrees for approval before deleting anything. |

## Deploy and live proof (26 Nov 2026, ~21:45-22:05 SAST)
- Backup first: `.tmp/backups/cip_20261126_205640_pre-step1-4a.dump` (3.4 GB, `pg_dump -Fc` exit 0, PGDMP header checked; `pg_restore --list` was denied by the guard, so a restore test was not run).
- Deploy `scripts\cip-deploy.ps1 -Execute`: `ca8f5f7f` to `f4feb367`, build OK, api/worker/web healthy, `/health/ready` 200, web 200 twice 60 s apart, launch counts unchanged. Record: `%LOCALAPPDATA%\CIP\deploys\deploy-20261126-215042.json`.
- Live render on http://127.0.0.1:3000 as the audit user, dark and light, text measurements only (script `.tmp/live_proof.py`, untracked):
  - Nav rail: 244px, 16 groups, no wrapped label, no label/chevron overlap, no page horizontal scroll. The active group's heading is brighter when collapsed (dark 0.96 vs 0.82 alpha).
  - Titles: `/dashboard` and `/listing-capture` are a real `h1` at 27px. `/promotions` is an `h1` at 15px and `/directory` an `h5` at 15px (known 4b debt). Body gradient is valid in both modes (dark cyan 0.15, light blue 0.12). No console errors.
  - Monitored listings (`/listing-capture`): price matrix present; labels "Sell-out · Jul 2026" and "Sell-out · Dec 2025", line-up label present, "Below SRP" present; no "Cheapest at", no "SRP source not yet chosen", no "pending Warren".
  - NOT done: element-by-element comparison against the mockup PNGs and the dashboard-v2 mockup (the checks above are measurements, not a mockup match). Status is VERIFIED_WITH_LIMITATIONS: the independent consult was Opus reviewing Sonnet's code (and Sonnet reviewing Opus's), not a Codex or other-family model; Codex is out of usage until 27 Nov 14:15 SAST.

## Warren's decisions this session (verbatim)
- SRP rule: "use sell out price, fall back to Line up price, fall back to website off promo price."
- Line-up VAT: "Can you not see that Line up has price ex VAT and including vat and Margin?" Use the VAT-inclusive figure (`pricing_chain_json.inputs.srp_inc_vat_local`, fallback `msrp_local`).
- Unaccepted draft line-ups as an SRP: "NO". Validated and pending_review: "ONLY ACCEPTED ONES FFS". ASSUMPTION: "accepted" means accepted or any later status (`ACCEPTED_OR_LATER_STATUSES` in `lineup_case_status.py`); excluding po_pending/po_issued would remove every live line-up SRP.
- Sell-out label shows its period: "Yes please" (for example "Sell-out · Jul 2026").
- Nav rail: "How about you do what was told and follow the mockup layouts?" Rail is 244px (headings need about 154px against a 144px box at 172px). Active group heading is highlighted when collapsed ("YES"). Mobile drawer width: "I DONT FUCKING CARE ABOUT THE PHONE" (left as is). Fixed footer copy "Your workspace / Only data you can access": "NO" (ASSUMPTION: no change; the question text was lost in the context reset, so confirm if it matters).
- Planner proof: "dont worry when I upload the rest of the cases I will check if it works. We will go onne page at a time eventually." Live has no open customer sell-through cases (310 cases, none open).
- Targets: Warren asked "you tell me what is better?". Recommendation, not yet confirmed: a guided "Add tile" builder dialog on the Dashboard reusing the existing storage (BACKLOG-269 slices 1 and 2 shipped 24 Nov; there is no standalone Targets page). A builder should first check for an existing `/targets` route. Mockups: `docs/design/dashboard-v2/targets-builder.html`.

## Open items for Step 4b (do not lose)
- `PageHeader.tsx` renders `variant="h1" component="h5"` because `PageHeader.test.tsx` asserts the h5 element; moving to a real h1 needs that test edit with Warren's say.
- Dead `data-cip-tone` selector in the theme.
- `/promotions` and `/directory` titles at 15px; Panel title weight and shadow differ from the mockup.
- A three-digit count chip beside "PROMOTIONS & FUNDING" could overflow the 244px rail (4px spare).
- Warren asked whether the new theme looks better and more premium than the current one: answer from the rendered comparison, not from source.

## Open items for Steps 1/3
- After Step 1 is live: mount the site-confirm bar on Monitored listings, then Step 3b live activation (backup and clone proof before any live write; auto-discovery on live whenever services are up; Takealot and Amazon rediscovered; nothing auto-linked without exact evidence).
- One Takealot cell shows 229 against a sell-out SRP of 21,999 (looks like a capture/parse issue upstream; not changed).
- Live SRP coverage at 09415710 (read-only): 100 cells with a listing; sell-out 30, line-up 45, website 1, none 24 (all Evetech); 21 below SRP. The website tier has only 1 value because no separate regular-price column exists (`parse_flags.rrp_listing_price` only).
- "Cheapest at" tiles were removed per the step brief (ASSUMPTION A3); confirm with Warren that this removal is intended, since the rule is "no screen removed".

## EIF notes
- Programme CLI runs bare: `python .eif/runtime/programme/program.py ...` (use `--project <worktree>`). Node ids: Step 0 N-0120, Step 1 N-0121, Step 2 N-0122, Step 3 N-0123, 4a N-0124. Ledger sequence collisions are likely across worktrees.
- Independent consult: Codex is out of usage until 27 Nov 14:15 SAST; reviews so far are cross-model Claude (Opus reviewing Sonnet and the reverse). Report "verified with limitations", never "done", unless an independent consult by another model family happens.
- The scratch that must never be committed: `.step1-scratch/`, `_proof4a/`, `apps/web/.next-4a*`, `next-env.d.ts`, `tsconfig.json`, `_n0124_payload.json`, `.eif/runs/`, `.tmp/`.
