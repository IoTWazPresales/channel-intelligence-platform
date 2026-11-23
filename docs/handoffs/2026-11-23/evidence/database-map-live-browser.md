# Database-map live-browser release verification

2026-11-22. **VERIFIED_WITH_LIMITATIONS — live UI smoke passed, actual exit0.** This verifier independently executed the existing reviewed lifecycle-browser.cjs in a fresh browser context against `http://127.0.0.1:3000`.

Before execution, primary HEAD `c685bf63147f7db5d3a5050dcf3c9dcc23229abc`, on-disk BUILD_ID `CbNqqIUC9jWVb7H6po90e`, live listenerPID84280 and its creation/Next start command matched the release identity. Root owns the release and service process. No harness, product, service or configuration change was performed by this verifier.

Actual output: `live-browser-1.log` and `live-browser-1.exit.txt` (0). Unique unchanged raw results/geometry/catalog/PNG evidence: `../lifecycle-live-c685bf63-1/`. The harness's generic result string is CANDIDATE_BROWSER_VERIFIED_WITH_LIMITATIONS; the recorded base/phase/source/build unambiguously identify this live3000 run.

Seven checks passed:

1. Owning route requires normal sign-in; actual admin sign-in used the ordinary application flow.
2. UI status and initial rendered node IDs match the real142-table/285-FK-link catalog.
3. Fit matches with neighbour focus gives the matching user_ui_layout card340px width at zoom1. The screenshot was visually inspected and shows readable name, types, columns and PK/FK markers.
4. Focused no-match search shows the empty message, disables fit and removes nodes/minimap, with finite SVG attributes.
5. Clearing search while focus stays checked restores the complete142-node graph and minimap.
6. Three repeated empty/focus-toggle/restore cycles retain finite SVG, minimap behavior and every node's exact world coordinates.
7. Standard context fit retains three context tables and exact catalog FK links; a real mouse click displays the selected relationship's columns.

After execution, raw results were independently rechecked programmatically: all seven checks present, all recorded SVG attributes finite, all142 node coordinates preserved, focus-card340px/zoom1 and the three-node FK context. There were zero authenticated console errors, zero page exceptions and zero blocked write attempts. Four intentional anonymous401 console resource errors remain retained separately; they are not relabeled as zero total console errors.

No Save, drag, reset or durable layout/business-data mutation was attempted in this live browser session. Normal sign-in is the permitted application authentication flow. Clone drag/Save/reload/account isolation has separate real-app ASGI persistence and read-only cleanup evidence; this live run does not repeat those writes. Root's release and60-second stability collection are separate evidence and are not certified by this browser-only report. CURRENT/CONTEXT updates remain root-owned.