# E1 independent verification — VERIFIED_WITH_LIMITATIONS

Review run: `RUN-20261025-N0115-E1-VER-ASTRA`.
Implementation run: `RUN-20261025-N0115-E1-CODEX`.
Completed 26 October 2026, resumed from the 25 October review. Assigned model separation: implementing root GPT-6.1-Sol; reviewing agent GPT-6-Astra, in a separate agent context. This records the actual invocation provenance supplied by the orchestrator, not independently measured runtime model attestation. The reviewer made no implementation edits.

Bounded scope: governed CPOR filter fidelity in a2_cpor.py, portfolio_intelligence.py, cache.py and test_cpor_query_filter_fidelity.py. No product edits, ledger mutation, quality pass, production connection, service action or migration by this reviewer.

**Verdict: the bounded E1 filter-fidelity correction is VERIFIED_WITH_LIMITATIONS. No unresolved blocking defect was found in this final E1 diff.** This is not N-0115 acceptance, original-scope completion, a release decision, or completion of all R3 gates. Root remains the sole ledger and memory writer.

## Scope and canonical contract

Compared the working diff to HEAD `d069f86c9232a735b87c64bb8f3fe3c7b5916b08` on `feat/ns-2-brief-nav-collapse`, the three A2 catalog entries, governed planner/adapter, existing portfolio tests, query engine, report delivery/export code and authenticated fixture. The canonical owner remains `services/cpor/portfolio_intelligence.py`; the query handler extends that reader rather than creating another commercial calculation path.

| Trigger | Read path | Write/commit consequence in this review |
|---|---|---|
| v1 query | execute_query -> handle_a2 -> request AsyncSession.run_sync -> portfolio reader | No product write |
| v2 governed query | run_v2 -> _run_governed -> v1 engine/handler | Same reader; rows reshaped, sorted/limited by existing adapter |
| Ad-hoc/saved export | report export endpoint -> applicable v1/v2 query -> serializer | Test artifact bytes only |
| Manual/scheduled delivery function | deliver_saved_report -> applicable query -> inbox ReportDelivery | Fictional cip_test rows only, inside rollback fixtures; no external send |

The former handler opened a separate sync SessionLocal, aggregated the full portfolio, then conditionally trimmed already-aggregated rows; totals and cross-grain filters could disagree. The final handler uses the request session and passes tenant/customer/BU into the canonical reader. SQL filters cases by tenant and customer; BU selects lines before every additive/ratio rollup. USD/ZAR support computation, voided/zero-estimate exclusions, ratios and null denominator behavior remain the existing formulas.

## Findings resolved during review

1. **MAJOR, resolved — warm cache bypassed refusal.** The initial `_canonicalize_filters` removed null/blank values. Warming `{}` then requesting `bu=''`, `bu=None`, `unexpected=None`, `product_line=''` or `customer_id=''` returned `ok`, value100 and cache hit; cold execution refused each. `astra_cache_probe_initial.txt` records all five counterexamples. Final `cache.py:93` preserves the supplied entries and the v3 namespace avoids earlier cached envelopes. `astra_cache_probe_final.txt` shows all five warm and cold calls refusing, with no warm hit. The SQL regression additionally checks `unexpected=''`.
2. **Scoped supplemental contract risk, resolved.** The new service parameters originally left `include_incremental=True` able to attach a separately unfiltered incremental summary. The governed handler already opted out, so this was not a demonstrated authenticated data leak. Final `portfolio_intelligence.py:47,254` automatically omits that supplement whenever tenant/customer/BU scope is supplied. Independent `astra_supplemental_probe.py` proves tenant, customer, BU and explicit include=True scoped calls do not invoke it; the no-argument owner call still does. The probe uses fictional objects/mocked I/O, with database connections vetoed; it verifies dispatch/contract behavior, not SQL isolation.

## Independently executed evidence

Exact approved test command from the repository root:

```powershell
apps/api/.venv/Scripts/python.exe apps/api/scripts/db_on.py pytest tests/test_cpor_query_filter_fidelity.py tests/test_cpor_portfolio_intelligence.py
```

Final result: **11 passed in 28.76s, exit0**, `astra_focused_final.txt`. The earlier initial-source run was11 passed in56.81s (`astra_focused_initial.txt`); it does not replace final-source evidence. No full suite was repeated by this reviewer.

The final focused run exercised real PostgreSQL on cip_test, three governed metrics × three advertised single grains × six filter scenarios (54 v1 cases, with corresponding v2 results). Scenarios include unfiltered, BU normalization, customer, customer∩BU, missing customer and missing BU. It checks filtered additive scorecards and row sums, ratios from the filtered denominator, null zero-match ratios, empty grouped rows and v1/v2 agreement. Unsupported filter keys, malformed/multi-valued inputs, conflicting BU aliases, dates and unsupported cross-tab refusals are exercised separately. The existing pure service tests retain support/FX/voided-line behavior.

Authenticated HTTP checks exercise real bearer auth through in-process ASGI, two tenants, admin/scoped/empty users and repeated query order, followed by saved v1/v2 XLSX export and manual delivery, and ad-hoc XLSX/PDF. The fixture asserts cip_test and a login without superuser/BYPASSRLS. Its savepoints remain under an outer rollback. Product-scope intersection checks use fresh ORM objects and transaction-local scope. This is API/SQL evidence, not browser smoke.

Independent pure probes use SQLAlchemy connection vetoes and no Redis connection: cache warm/cold counterexamples and final behavior; supplemental invocation behavior. Their scripts and initial/final logs are in this directory. Source hashes below and the ten-path `astra_source_sha256_final.json` bind these results to the final sources.

| E1 path | Final SHA-256 |
|---|---|
| apps/api/app/query/handlers/a2_cpor.py | 220efc0383eb2089fce0167b0e945e4f90a6ac2f5e10d5acdb4d1a0982985f71 |
| apps/api/app/services/cpor/portfolio_intelligence.py | 60ca08999b11fbf7c62840cd559b2707c24a8b523fecd5b64ed8f1cacc89969b |
| apps/api/app/query/cache.py | d4b9ddd2d591d0db08a102bae95cb58cc499b84c05c7ef5808134806a52dd9a6 |
| apps/api/tests/test_cpor_query_filter_fidelity.py | 5f098de8e257affb828ce4fe6cf666086758127347f67a58bbbec7a8f7b8e004 |

## Limits and authority

- Runtime capabilities remain **UNVERIFIED**, including verifier-separation enforcement; no guard is relabelled ENFORCED. Model separation is recorded from agent invocation, not runtime attestation. This bounded result does not complete overall R3 verification.
- Authenticated tenant/product checks are useful application/forced-RLS evidence, not non-owner PostgreSQL-role proof. No roles/grants were created. Recipient scope, actual scheduler execution without request context, pooled resets across the full security matrix, and broader background-delivery policy remain outside E1. The direct `user=None` delivery fixture retains its tenant ContextVar, so it is not scheduler isolation proof.
- No live browser or production smoke was performed. No production cip connection, migration, service start/restart, deployment, remote push, acceptance or ledger mutation was performed by this reviewer. Test inbox writes were rolled back. Pure probes did not connect to any database.
- Large-cardinality performance, original CPOR/domain decisions, model calendar/overlay functionality and all other original N-0115 requirements remain open as recorded in the programme matrix. This review does not retire them. Existing unrelated export/saved-report fidelity issues are not declared resolved by the bounded caller checks.
- Root's full-suite, lint, typecheck and build results are separate implementation evidence; they were not independently rerun or granted a pass here. Root must preserve their actual final-source cutoff and any unrelated failures.
- `.cursor/rules/engineering-rules.mdc` was absent; the required read was attempted and the missing-file limitation reported. Other onboarding, identity, work-item, governance and specialist contracts were read. This reviewer wrote only its audit artifacts and did not alter protected ledger/runtime state or inherited dirty files. Ledger prefix preservation is root's separate measured closeout responsibility.
