# E4 saved-query execution fidelity

Base pushed d2200cb1f139d28642ad44a79dc6403f30d28c34 (tested E3).
Implementation run RUN-20261026-N0116-E4-CODEX. User subsequently requested a
bounded closeout to avoid further usage; stop after this tested checkpoint and
retain E5-E10 as the original open frontier.

## Canonical paths and correction

| Trigger | Canonical API/service | Writer/commit |
| --- | --- | --- |
| Promote | dashboards widget promote, check_definition | Saved report + link in one transaction |
| PDF/XLSX | reports saved export, saved_report_payload | Read/export only |
| Send/schedule/import | report_delivery, existing runner | Existing per-delivery commit |
| Reports download | saved GET for v2; ad-hoc POST for legacy form | No new writer |

Other screen writes (widget add/edit/duplicate/layout/delete, report save/delete/
publish/pin and schedule creation) retain their existing writers. No importer or
fact writer is involved. Root owns backend, ledger, memory and commits. The
frontend specialist owned its assigned web files; no overlapping product writes.

Initial14 backend regressions failed before production changes. A non-default
monthly grouping additionally reproduced a quarterly export. Explicit sort/limit
now prevent false v1 dispatch, including already-persisted incorrect flags.
Export and delivery carry period_grain; legacy ad-hoc export accepts it too.

The existing promotion endpoint accepts the exact effective execution request
from canonical requestFor, including unsaved/transient selections, own filter
intersections and filter/date exceptions. It validates immutable query shape,
retained own restrictions, nonempty selections and valid complete dates. The
saved question captures actual selected dates as explicit fixed dates, with a
visible explanation; no rolling policy is invented. Inherited context required
but absent is refused. The reusable widget remains unchanged.

Reports downloads a saved v2 definition through the existing saved export route.
It shows the saved question honestly and guards the lossy legacy Run/Save form.
Download, send, schedule and explicit start-new-question remain available.
This read-only saved-definition mode includes migrated v1-expressible definitions;
legacy edit-copy/Run for those definitions is a disclosed UX limitation. A full
v2 report editor remains excluded by S20; NULL-definition legacy editing remains.

## Review-driven regressions

The first correction passed13/14; the remaining real import-event test proved
governed-v2 execution dropped skip_cache and reused70 instead of fixture100.
Forwarding the canonical bypass flag fixed it without altering amounts/formulas.

Separate Astra preliminary review then found two additional failures:

- A valid own bu:[null] restriction could be omitted or confused with literal
  text 'None'. Root reproduced three failures before correcting key presence
  and typed-null comparisons. The server retains valid null filtering. Because
  the dashboard picker cannot represent null, requestFor explicitly refuses such
  owned filters instead of silently omitting them. Four frontend red cases are
  preserved; this UI limitation is explicit, not a claim of full null editing.
- Implicit ordering/default500 were lost by v1-compatible saved execution. A
  real rollback fixture with502 product groups exported all502 in legacy key
  order, whereas the card returned500 in value order. Shared present_handler_rows
  now supplies model default value/period order, stable dimension ties, governed
  handler order and the display cap. Shared saved_report_payload uses it for both
  export and delivery. Compatible definitions retain canonical legacy handlers
  and validation; NULL-definition legacy reports remain unchanged. Totals and
  financial definitions are untouched; row_count/truncated metadata is explicit.

## Evidence and limits

final-summary.json records fresh final gate counts when completed. Earlier logs
are historical stages, not substituted for final evidence. Browser proof uses
the cip_test-only bearer/outer-rollback harness, separate web3107 and isolated
.tmp output. It checks real card13/total112, exact promotion context, saved PDF/
XLSX bytes and inbox total/window; no host API/worker restart or production data.

Astra's preliminary report remains its original FAILED-pending-correction
artifact. The final two corrections are root-tested and separately re-executed
as self-verification; reviewers hit usage limits, so no independent final pass
or full R3 is claimed. Review separation earlier in the unit does not prove
final-source independence. Runtime/model attestation and non-owner/concurrency
proof remain unverified. The E4 lease elapsed during the usage interruption;
root checked state/integrity and reacquired it through the supported CLI before
further edits. No uninterrupted runtime enforcement claim is made.

The original89-event prefix is preserved. No production connection/write,
migration0048 application, API/worker restart, grant/identity, deploy/main or
operator acceptance occurs. Original business decisions and E5-E10 requirements
remain open. Existing legacy tenant semantic restrictions/model counterpart work
is retained at E6; this unit does not route compatible handlers around it.
