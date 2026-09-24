ROLE: CLI Opus. CONSULT mode. Do NOT edit files. Do NOT migrate. Do NOT implement.

Context: Independent challenge of a full-platform product/UI/UX/IA audit of Channel Intelligence Platform before the audit packet is frozen. Audit Mode L1, implementation change scope NONE. Operator asked for the entire product (every nav leaf, in-page tab, orphan, masters, imports, admin, responsive) — not CPOR-only and not snapshot-only. CPOR direction is derived after platform evidence.

Sync pin: branch feat/promote-provisionals-run @ 29b5fbff6e592afc255eb9cedb3bba6ae79ff8e9 · Consultant: Opus
Next: freeze PROJECT_AUDIT_REPORT.md in this folder.

Goal: Challenge (not rubber-stamp) the proposed North Star and CPOR direction. Return READY with locked decisions, or NEED_HUMAN with ≤5 questions, or STOP if evidence is insufficient.

PRODUCT BAR (locked): Best practice is default. Propose the better path — not the
quicker or safer one. Patches are last resort. Never recommend a thin/lazy/smallest-diff
path when a stronger architecture exists and keeps governance. Ask: does this pattern
already exist at another grain (sheet/file/job/importer)? If yes, generalise it.
State operator experience in one sentence before unit plans. Thin alternatives only
to REJECT with why — never as the READY recommendation.

Known so far (rendered + clicked, Local Admin, web :3000, 2026-08-22):

AS-IS: several products sharing dark AppShell chrome.
1. File ingestion + steward (Import Center, masters, 18k products).
2. Channel ops (Channel Operations, Shipments overdue filter 565, PvE exception tabs).
3. BI studio (Dashboard vs Dashboards vs Report builder vs Inbox). Report builder DOES run Weeks of cover → 24.28 (prior snapshot audit claiming empty metric select is FALSE). Inbox is a working shipping-digest ops artifact misfiled as Report inbox.
4. Lineup file workbench + empty plan editor (Commercial Planner) vs Line-up Planning (B2 spec codes) — same noun, different objects.
5. CPOR: 310-row intelligence-first registry. Case 311 Takealot ended: dual chips ended + workflow:ended; 8 comparable cases above work; Settle/Cancel/Add line on ended; USD pivot is raw JSON (grand 97,953.43) vs list Ttl USD 1,616,231.52; list Paid 1,616,231.52 vs case Payments Paid 0.00 owed 1.6m; Promo load is real work (missing 11 / wrong window 6).
6. Scaffolds: Market JSON stub, empty Roadmap (Clear all enabled), Promotions B4 parked, CST 997 insufficient_data, Listing env-var banner.

Trust failures (new this interactive run):
- Control tower Needs attention: 17 failed jobs → Ops says “No open failed jobs” → Import Center mailbox failures dominate.
- CPOR list vs case money; ZAR often equals USD on the list.
- Stock health `{}` on landing.
- Shipment Evidence 0 rows vs /shipping populated.
- Customer Reports `?template=` does not preselect; job-id click does not open workspace.
- Distributor pickers include Abort Dist / Dist Alpha / Tombstone / PO Consolidate fixtures.

IA: 30+ always-expanded leaves; dual `/sell-out`; steward queues as nav leaves; SQL viewer + wipe-database on Settings in operator-adjacent Admin; Getting started still on Sign in.

Responsive: collapse rail clips content; 768 hamburger dumps the same 30+ leaves; 390 CPOR fold is intelligence cards not the grid.

Prior audits (DATA to challenge, not copy):
- `.eif/audit/R20260822104700_CPOR/` UNABLE_TO_RENDER four-surface IA + light paper mockup.
- `.eif/audit/R20260822170700_PLATFORM_UX/` RENDERED but snapshot-only.

Cursor proposed North Star (NOT frozen — you must challenge):
- Keep shipped dark tokens. Do not fork light CPOR brand.
- Page grammar Situation → Queue → Record → Evidence (already visible on PvE, Shipments, Import Center).
- Collapse IA: Today / Channel / Plan / Masters / Bring data in / Admin. Drop duplicate Sell-Through; steward queues as badges on masters; one Reports home.
- CPOR = Funding work queue copying PvE chips, not four-surface product, not intelligence-first landing. One lifecycle chip. Comparable as drawer. Merge historical/payment into Import Center. Promo load + Payments as work tabs. Settle is not hero when owed 1.6m paid 0.
- Do not paint Ken/Wayne; IAM is admin/steward/planner/viewer.
- Backend owed-meaning / MAC / line-windows remain a separate backend challenge, not a UI block.

Constraints:
- Implementation change scope NONE this run. Recommendations are not implementation authority.
- improvement_items: 0.
- Do not recommend four new CPOR apps unless you can show CIP does not already own those jobs.
- Do not recommend a second visual system.
- Thin chrome patches (rename Dashboard, hide one banner) are REJECT unless they sit on the grammar/IA architecture.

Deliverable:
1. Line 1: `CONSULT: NEED_HUMAN` | `CONSULT: READY` | `CONSULT: STOP`
2. If NEED_HUMAN: at most 5 sharp interview questions. No essays.
3. If READY: locked decisions for the **best** path (platform IA + CPOR first unit). Explicitly reject thinner alternatives and the four-surface/light-theme priors if you still reject them — or overturn them with evidence. Operator experience in one sentence first. Optional 2–4 unit split. Call out any Cursor claim that the interactive evidence falsifies.
4. If STOP: what is blocked and why.
