# Database-map lifecycle correction and acceptance

2026-11-22. Candidate `567f8bfa01866ace66385a74bc66d7eadb443482`.
**VERIFIED WITH LIMITATIONS: source gates, candidate/live browser, clone persistence and live stability passed.**

## Correction and source evidence

Installed ReactFlow12.8.5 copies controlled node props into its store in a passive effect. MiniMap checks that its lookup has entries, then computes bounds from nonhidden entries. The old parent-prop guard could mount MiniMap while that store still held only hidden nodes. A private wrapper now uses public `useNodes` to gate from the same internal visibility. Graph lifetime, positions, theme, layout snapshot and existing writer are preserved.

- Three files changed in this commit: page, existing mock tests, real-provider/store/MiniMap regression.
- Regression before: exit1, eight invalid SVG attributes captured in intermediate commits (`regression-before.log`).
- After:12 focused tests exit0. Separate reviewer independently reproduced12pass and found no blocker (`independent-review/review.md`). Changed-file lint and nonincremental types exit0.
- Clean detached candidate: full lint0errors/48baseline warnings, nonincremental types0, production build0. BUILD_ID `SyuZjgxpcsG9oHK6b1-1J` (`full-verification/`).
- Full unfiltered web suite: exit0,291files/1818tests,623.31s; verified process-local Node temporary directory; no retry/filtering/config changes or error suppression.

## Actual production-browser candidate

`http://127.0.0.1:3107`, standard foreground production entrypoint, owned PID38448. Source/build/process identity: `production-server.json`.

Actual exit0; seven checks in `../lifecycle-candidate-567f8bfa-1/results.json`:

- Normal sign-in required; real catalog matches142tables/285FKlinks.
- Focused Fit matches shows the matching card340px wide at zoom1.
- Empty focused search removes MiniMap; clear restores graph and MiniMap.
- Three additional empty/restore/focus-toggle cycles preserve all142 node coordinates; settled SVG remains finite.
- Actual mouse selection of a catalog FK shows its exact columns.
- Zero authenticated console errors, page errors or blocked business-write attempts. Four deliberate pre-login401 console errors retained.

Root executed the browser and inspected pixels. Separate verifier sampled artifacts, geometry, assertions and screenshot; it did not independently rerun the browser. Original23f browser failures remain FAILED and unchanged.

## Browser Save/reload/isolation on disposable clone

Target only `cip_ui_migrate_20261122_1df81d9e4dcb`, application role `cip`. Production UI uses real owning application APIs through HTTPX ASGI IPC; no API listener, lifespan, dependency overrides or pollers. Four unrelated shell GET readers are explicitly stubbed. Real fixture sessions remain in RAM/pipes/ephemeral browser storage. This does not test password login/logout, the Next HTTP proxy for Save, or retained-client account switching.

- First run remains FAILED: real drag/expand/Save200, then an invalid harness width>330 assertion for an expanded card in a two-table fit. Cleanup/source checks succeeded. Post-framing full-value assertion was not reached.
- Reviewer checked screenshot/error and a harness-only correction to wait for an actionable stable title. Source product was unchanged. Initial and retry artifact reviews/hashes retained.
- Corrected retry actualexit0: `browser-persistence-run-2.json`, result `CLONE_BROWSER_LAYOUT_VERIFIED_WITH_LIMITATIONS`.
- Five browser records: A drag+expand+Save; A reload restores entire saved value, coordinates and expansion; B saves a separate collapsed layout; another tenant sees neither; returning to A restores A after B saves the same key.
- All17 core responses200; zero console errors/page errors/blocked requests. Separate read-only DB connection confirms exactly two committed layouts equal the browser-submitted values before cleanup.
- Exact fixture cleanup restores tenant1/app_user3/auth_session135/layout0 and all four full-row digests. Source layout preferences read-only/unchanged.
- Separate verifier independently reran the original read-only preflight and compared fresh counts/digests against cleanup and source-after evidence: exact match (`full-verification/clone-after-browser-comparison.json`). This rechecks cleanup; it is not another browser execution.

## Delivery

Integrated/pushed at c685bf63147f7db5d3a5050dcf3c9dcc23229abc; integration product tree compared identical to567. Web-only build/restart actualexit0, live BUILD_ID CbNqqIUC9jWVb7H6po90e; launches5->6 and others unchanged. Separate verifier independently executed all seven actual live3000 browser checks, exit0 (live-browser-verification.md). Native web/API health200 and all six component states/counts/build stable across82.349s (live-web-stability.json). Initial failed stability collector used an unexported helper before querying; retained separately, corrected collector used fresh files. Candidate3107PID38448 stopped after ownership checks. API/worker unchanged; no main promotion.
