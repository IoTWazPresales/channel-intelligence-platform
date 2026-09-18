# GOV-008 handover — N-0028 and N-0029

Independent review of **N-0028** and **N-0029**. Review **one node per session**. Do not complete either node in the review session. Do not batch them.

This note supersedes `docs/design/gov-008-n0027-n0029-handover.md` for N-0028 and N-0029. N-0027 is already complete (`GOV008_N0027_20260916` / `gov-022`).

## One node per review

Never review N-0028 and N-0029 in the same run. The last batch review
(`GOV008_N0025_N0029_20260915`) poisoned N-0028 with a dirty tree and a
Panel/PanelRow pass against an AC that no longer exists.

## Ignore stale evidence

Ignore `.eif/audit/GOV008_N0025_N0029_20260915/` and
`.eif/runs/GOV008_N0025_N0029_20260915/` entirely. They are stale. Do not
cite their verdicts, signatures, or Panel/PanelRow tree.

## Fresh run and actor each time

New run id. New actor. Do not reuse `inv-018`, `gov-001`, `gov-021`,
`gov-022`, or any prior `gov-0NN` actor.

## Viewports

Render **1280×800** and **390×844** on a **clean tree**. If `browser_resize`
is unavailable, say so explicitly. Playwright MCP / `cursor-ide-browser`
only. Never `browser_cdp`. Never `browser_run_code_unsafe`. Direct
navigation is not proof.

## N-0028 — click the cards

1. Sign in as **admin**. Open Start work. Click the actual Start work
   **ActionCards**. Assert the **URL changes** after each click.
2. Sign in as **viewer**. Repeat the same clicks. Prove role gating from
   those clicks, not by reading `startWork.ts`.
3. Direct navigation to destination URLs is not proof and has never been
   established across five sessions.

## N-0029 — Case ID deep link

Include the `aee82a7` **`?code=` exact-Case-ID** behaviour:

- Payment-evidence-import reads `?code=` as an exact Case ID.
- Overlay `?code=` returns `focus_rows`.
- No mint. No fuzzy match.
- Unmatched codes stay unmatched (live example: `C19A50693` → 1 applied
  unlinked row). Do not treat unmatched as a case create.

## Do not

- Complete the node.
- Review both nodes in one session.
- Cite `GOV008_N0025_N0029_20260915`.
- Treat reading `startWork.ts` as role-gating proof.
- Run GOV-008 against a dirty tree.
