# Partial external verification — N-0116

Reviewer run `RUN-20261024-N0116-VER-ASTRA`, fresh context, explicitly selected different model
`gpt-6-astra` under GOV-008's R3 independence instruction. This record is written by the implementing
orchestrator from delivered reviewer messages; it is NOT a final report or verdict from that reviewer.

The reviewer reported an independently executed six-file sample: 42 tests passed, exit 0, 133.46s
(advancedShape 12, fit 11, api 10, useDashboardRun 2, ViewRowsDrawer 3, clickFilters 4).
It inspected accepted light/desktop and dark/mobile screenshots as fixture-only evidence.

Findings delivered before the reviewer stopped:

1. Missing catalog metadata: v2 requests could drop dashboard filters; advanced visuals could call
   measureHeading without a measure. Root added blocked planning, safe body state, legacy-edit guard
   and reload action, with null/missing-metadata regressions. Reviewer inspected that narrow fix.
2. Hidden own filters survived model changes even though controls were hidden. Root now clears them
   when changing model/governed family; added real workspace/editor regression.
3. Non-additive Other series: reviewer executed actual shape.ts via in-memory transpilation and
   observed nine .8-rate rows become seven .8 series plus Other(2)=1.6 (server total .8). Root removed
   the manufactured sum, preserves named grouped values/nulls and shows an omitted-category count;
   added a regression. This fix still needs completed independent review.

The agent then returned: usage limit reached, retry availability 17:31. No final verification artifact
or verdict was delivered. Root continued independent implementation/testing tasks. A completed
independent GOV-008 gate, operator acceptance and node completion are NOT claimed.
