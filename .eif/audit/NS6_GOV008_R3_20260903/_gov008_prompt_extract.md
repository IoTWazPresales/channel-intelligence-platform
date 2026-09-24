<timestamp>Thursday, Sep 3, 2026, 2:23 PM (UTC+2)</timestamp>
<user_query>
You are acting as GOV-008 — an INDEPENDENT verification reviewer for the Channel Intelligence Platform (CIP) programme. Repo: C:\Users\warren_eliason\channel-intelligence-platform (Windows, PowerShell). You did not author the artifact under review. Your job is to verify, not to redesign. You must be sceptical: a claim in a markdown file is a claim, not evidence; you must reproduce it yourself by rendering the prototype in a browser.

STRICT CONSTRAINTS
- Read-only on the repository EXCEPT you may create files under `.eif/audit/NS6_GOV008_R3_20260903/` (create the folder). Do NOT edit anything under `apps/`, `docs/`, `.eif/program/`, `.eif/runtime/`, or any other path. Do NOT run `python .eif/runtime/programme/program.py` or touch the programme ledger. Do NOT run git commands that change state. Do NOT run migrations, seeds, or anything touching the database.
- The web app is already running at http://localhost:3000. If it is not responding, report UNABLE_TO_RENDER with what you tried; do not start services.
- Use browser automation MCP tools (namespace `user-playwright` tools like browser_navigate, browser_snapshot, browser_take_screenshot, browser_resize, browser_click; or `cursor-ide-browser`). Use GetDynamicTools to discover schemas first. Save screenshots into `.eif/audit/NS6_GOV008_R3_20260903/renders/` (Playwright `browser_take_screenshot` accepts a filename; if it only saves to a default dir, record the path it returns).
- Do not fabricate. If you cannot verify something, say UNVERIFIED and why.

WHAT IS UNDER REVIEW
Programme node N-0013 "Full-platform IA architecture and buyer vocabulary approval" — a design-discovery node whose deliverable is a high-fidelity React design prototype ("design-lab") inside the real Next.js app, plus rendered evidence. The operator has ACCEPTED decision D-0008 (r3/r3.1 direction). Your review asks: "Does the prototype + evidence actually satisfy the design gate as claimed?" — NOT "should the product be redesigned again".

D-0008 (accepted) in summary: primary navigation = capability domains: Overview · Stock & Sell-through · Supply & Inbound · Planning · Promotions & Funding · Market & Listings · Data & Stewardship · Administration (admin only). Composed Overview (business dashboard + attention + pinned reports). Entity context panel (product/customer/case). Command palette + capability directory. Four-state leaf status vocabulary live / partial / substrate / planned (rail shows live+partial with partial marked; directory shows all four with a legend). "Commercial inputs" domain REMOVED. Promotions & Funding owns the whole cpor_case lifecycle (Promotion planner · Case book · Claims evidence · Payments · Plan templates · Terms & assumptions · Budget ledger[substrate]). Market & Listings = evidence domain (Monitored listings · Price history · Promotion activation · Feed proposals · Competitor mappings[partial] · Competitor prices[substrate] · Competitor listings[planned] · Listing quality/SEO[planned]). Nothing unbuilt rendered as working analytics; no fabricated uplift/elasticity/impact/confidence figures. Old rejected vocabulary (Brief · Plan · Position · Settlement · Actions · Imports as primary nav) must NOT appear as the primary IA.

FILES TO READ FIRST (claims to verify)
- `.eif/audit/NS_REDESIGN_R3_20260902/OPERATOR_SUMMARY.md` (context; r3.1 section at end)
- `.eif/audit/NS_REDESIGN_R3_20260902/DIRECTION.md`
- `.eif/audit/NS_REDESIGN_R3_20260902/commercial/COMMERCIAL_DIRECTION.md`
- `.eif/audit/NS_REDESIGN_R3_20260902/rendered-verification.md` and `.eif/audit/NS_REDESIGN_R3_20260902/commercial/rendered-verification.md` (author's rendered claims — you must reproduce a representative sample, at least 10 claims, including at least 3 at mobile 390x844)
- `.eif/audit/NS_REDESIGN_R3_20260902/CONCEPTS.md` (alternative concepts compared — for design_divergence)
- `.eif/audit/NS_REDESIGN_R3_20260902/FAULT_FINDINGS.md` (for design_sameness_review)
- `.eif/audit/NS_REDESIGN_R3_20260902/commercial/CONSULT_SEED.md` and `CONSULT_RESPONSE.md` (CONSULT with other model)
- Prototype source: `apps/web/src/design-lab/**` and routes `apps/web/src/app/(design-lab)/design-lab/**` — confirm it is a React prototype in the real stack (MUI etc.), not standalone HTML; confirm it uses fixtures only (no production API writes); confirm labNav.ts has the four-state LeafStatus.

ROUTES TO RENDER (desktop 1280x800 and mobile 390x844 for at least the shell, overview, funding, market, directory)
http://localhost:3000/design-lab , /design-lab/stock , /design-lab/supply , /design-lab/planning , /design-lab/funding (and its lenses — look for planner/templates/budgets lens controls or query params like ?lens=planner), /design-lab/market , /design-lab/data , /design-lab/admin , /design-lab/reports , /design-lab/directory. Exercise the command palette (look for a search/palette control or keyboard shortcut described in the source, e.g. Ctrl+K or "/") and at least one entity context panel opening (click a product/customer/case figure). Note: if the app requires login, try navigating; if you hit a login page, report UNABLE_TO_RENDER for those routes (do not guess credentials) — but first check whether `(design-lab)` route group is outside auth middleware by reading `apps/web/src/middleware.ts`.

VERDICTS REQUIRED — write `.eif/audit/NS6_GOV008_R3_20260903/independent-rendered-review.md` with these sections, each ending in a one-word verdict PASS / FAIL / UNVERIFIED and citing your own screenshots (filename + viewport) or file:line evidence:
1. `design_artifact_class` — is the delivered artifact a high_fidelity interactive React prototype in the real apps/web stack with fixture data (not standalone HTML/CSS)? 
2. `design_divergence` — were materially different concepts compared with evidence before convergence, and was a CONSULT with genuine model separation recorded (different model, separate process)? Cite the files; do not accept the claim without opening them.
3. `design_sameness_review` — did the r3.1 work challenge its own visual vocabulary / prior direction (FAULT_FINDINGS, D-0007→D-0008 delta) rather than copying? Is the four-state status honest in the rendered UI (substrate/planned leaves not shown as working analytics)?
4. `rendered_comparison` — does the rendered prototype match the D-0008 statement (domains, leaves, statuses, removed "Commercial inputs", no rejected primary vocabulary, no fabricated impact/uplift/confidence numbers)? List every discrepancy you find.
5. `content` — nouns/labels: Promotions & Funding, Market & Listings, "Partly built / Data only / Planned" style labels present and consistent between rail, directory, palette.
6. `verification.rendered` — do the author's rendered-verification claims reproduce? Table: claim | your observation | screenshot | match yes/no.
7. `verification.referent` — referent = D-0008 statement + N-0013 acceptance criteria (listed in `.eif/program/PROGRAM.yaml` under N-0013 acceptance_criteria — you may READ that file, not write it). Does the artifact satisfy each acceptance criterion? Table per criterion.
8. Known design-lab inconsistencies you observe (e.g. list/detail totals disagreeing, competitor score explanation not reproducing the score, one customer's evidence appearing under another customer, stale N-0010 "Actions" copy). These are NOT fails of the design gate — they become implementation acceptance criteria — but list them precisely with screenshots.
9. Overall verdict for the design gate, with independence statement: "Reviewer = separate agent context (subagent), same model family as author; rendered independently in own browser session on 2026-09-03."

Be concrete, terse, evidence-first. Finish by returning a short summary of the 9 verdicts and the path to the review file.
</user_query>