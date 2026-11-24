# Implementation log — 24 Nov 2026 recovery

Index only. Each step writes its own file under `steps/`. Branches do not share those files.

Planner mock-up: pending from Warren. `docs/design/planner-mockup.png` was not in the main checkout on 2026-11-25.

Overnight rule (`00-EIF-FLOW.md` wins over the step prompts): session 1 does not merge or deploy. Live `cip` writes stay stopped.

| Step | Prompt file | Step log | Branch | PR | Status |
|---|---|---|---|---|---|
| 0 | `01-step0-process-rules.md` | `steps/01-step0-process-rules.md` | `docs/impl-process-rules-20261125` | compare URL after push | Session 1 in progress. Not merged. |
| 1 | `02-step1-listings-matrix-centrepiece.md` | `steps/02-step1-listings-matrix-centrepiece.md` | — | — | Not started |
| 2 | `03-step2-planner-calendar-sellthrough.md` | `steps/03-step2-planner-calendar-sellthrough.md` | — | — | Not started |
| 3 | `04-step3-discovery-libraries-autodiscover.md` | `steps/04-step3-discovery-libraries-autodiscover.md` | — | — | Not started |
| 3b | `04b-step3b-discovery-live-activation-and-readers.md` | `steps/04b-step3b-discovery-live-activation-and-readers.md` | — | — | Not started. Live writes deferred. |
| 4a | `05-step4a-theme-fixes.md` | `steps/05-step4a-theme-fixes.md` | — | — | Not started |
| 4b | `06-step4b-theme-shared-components.md` | `steps/06-step4b-theme-shared-components.md` | — | — | Not started |
| 5 | `07-step5-cleanup.md` | `steps/07-step5-cleanup.md` | — | — | Not started. Best last. |

EIF node for step 0: `N-0120` (explicit id; auto-id is broken, see the step log).
