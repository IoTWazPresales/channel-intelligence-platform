# N-0028 content remediation

The 2026-09-24 review failed AC2 because the steward card said "Resolve unmatched tokens / Unmatched tokens from imports, resolved in one place." That reads as the legacy mapping queue, and "in one place" contradicts job-scoped resolve.

The card now says:

- Label: Work the steward queue
- What: Unresolved entity tokens waiting as pipeline state, grouped by failure type; resolve them in the resolve workspace.
- Href: `/admin/mappings` (unchanged)

Same sentence the Data rail uses for the N-0027 failure-type queue. Vitest: `startWork.test.ts` and `StartWorkLaunch.test.tsx`, 8 passed.
