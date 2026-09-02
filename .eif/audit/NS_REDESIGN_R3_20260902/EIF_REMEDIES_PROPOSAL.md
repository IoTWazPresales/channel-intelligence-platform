# EIF remedies proposal — from proven defects in N-0013 r1/r2

Run `NS_REDESIGN_R3_20260902` · Status: **PROPOSAL** for the EIF repository
(`C:\AI\engineering-intelligence-framework`). **Not applied.** This session's guard declares only the CIP
repository as a root (FAULT_FINDINGS E-9), so no EIF file was written or read from here; the pointers below
are to the CIP-installed copy under `.eif/runtime/programme/` and must be re-located in the EIF repo before
applying. **Apply only after the CIP design evidence is frozen by commit** (sequence in §4) so this run's
evidence cannot be judged by a framework it rewrote.

Each remedy: defect → mechanism/file → change → failure prevented → cost → risk → class
(configuration / orchestration / governance / code).

## 1. Remedies

### R-1 Independence must be structural, not declared (E-1)

- **Mechanism:** `eif_program/independence.py` `_pass_provenance_ok`; event emission in `program.py` `event` command.
- **Change:** an independent verification event must carry a **session token** that the runtime issued to a
  *different* process/session (e.g. `program.py consult open --role gov-008` returns a one-time token; the
  verification event must present it; the runtime records `session_id`, `model_id`, `pid` of the emitter).
  Same-process or same-`session_id` as any implementation event on the node → `independence: DECLARED_ONLY`,
  never `ok`. `--actor` remains a label, not evidence.
- **Prevents:** one script emitting both implementation and "independent" verification (amend_n0013.py 118–126).
- **Cost:** ~1 day. **Risk:** low; existing events stay valid but are reclassified `DECLARED_ONLY`.
- **Class:** code + governance.

### R-2 Model separation is a recorded, checkable field (E-1)

- **Mechanism:** `independence.py`; `CONSULT.md` ladder; `RUNTIME_CAPABILITIES.md` row "Independent verifier separation".
- **Change:** verification events at R3+ must record `model_id` and `session_kind` (`same-session` /
  `other-session-same-model` / `other-model`). Policy: R3+ requires `other-model` when
  `MODEL_CAPABILITIES.md` lists an available alternative (this project lists `claude` CLI). If unavailable,
  the node must carry an accepted compensating control (`decision.record` with `kind: compensating_control`).
- **Prevents:** r1/r2 reviewing with the authoring model when Opus was installed and unused.
- **Cost:** 0.5 day. **Risk:** low. **Class:** configuration + governance.

### R-3 Enforce gates at PASS, not only at `complete` (E-2)

- **Mechanism:** `engine.h_status` (`gates_ok` only when `dest == 'complete'`); `h_quality`.
- **Change:** run `independence_ok` and evidence-pointer resolution **when a quality dimension is set to
  `pass`**; store the result on the record (`independence: ok | DECLARED_ONLY | none`,
  `evidence_resolved: true | false`). CURRENT/ROADMAP rendering prints `PASS (unverified independence)`
  instead of bare `PASS` when either check fails. `complete` still hard-gates.
- **Prevents:** operator reading PASS records that the runtime had never checked (rev 220 status).
- **Cost:** 0.5 day. **Risk:** medium — some existing PASS lines will re-render as unverified; that is the
  truthful state. **Class:** code.

### R-4 Decision states: `rejected` and `deferred` (E-3)

- **Mechanism:** `engine.h_decision_status` (`proposed | accepted | superseded`).
- **Change:** add `rejected` (terminal; requires `rationale` and `by: operator`) and `deferred`
  (non-terminal; requires `until` trigger text). Rendering shows the operator's verb. Migration: none
  needed; D-0004/D-0005 stay as recorded and can be annotated with `notes`.
- **Prevents:** rejection encoded as "supersedes" workarounds hiding operator intent.
- **Cost:** 0.5 day. **Risk:** low. **Class:** code + governance (Volume decision model).

### R-5 Quality `pass` requires a resolvable evidence pointer (E-4, E-5, E-6)

- **Mechanism:** `engine.h_quality`; evidence resolver (currently ADVISORY).
- **Change:** `state: pass` requires ≥1 `evidence` entry; each is resolved at write time:
  `path[:line]` must exist; for rendered claims a `.png` and a `viewport` field are mandatory. Unresolved →
  write succeeds with `state: pass_unverified` (never silent `pass`). Add `claim_kind: source | rendered |
  executed` so a source claim cannot satisfy a rendered dimension.
- **Prevents:** the `:focus-visible` assertion citing a stylesheet that lacked the rule; mobile PASS from a
  source read.
- **Cost:** 1 day. **Risk:** medium — stricter authoring; mitigated by `pass_unverified` still being writable.
- **Class:** code.

### R-6 Governance changes during a governed run are quarantined (E-7)

- **Mechanism:** `.cursor/hooks/eif_guard.py` CONTROL_PLANE_PROTECTED list; `manifest.json` hashing.
- **Change:** if any file under `.eif/runtime/**` or the guard itself is modified (hash ≠ manifest) while a
  node is `in_progress`, the runtime marks every event written after the modification as
  `framework_dirty: true` and refuses `complete` until the framework change is committed **in a separate
  commit with a `governance.change` event** referencing it. Rendering shows a banner.
- **Prevents:** self-validating runs (the run rewrote independence checks after recording evidence).
- **Cost:** 1 day. **Risk:** medium — friction for legitimate framework work; that friction is the control.
- **Class:** code + governance.

### R-7 Preservation gains a product-quality dimension (E-8)

- **Mechanism:** baseline (`BLN-*`) + `preservation` map; `conservation_gaps`.
- **Change:** baselines may carry **rendered reference frames** (`renders/baseline/<route>-<viewport>.png`)
  and a small **task set** (`journeys` with `route`, `task`, `expected visible outcome`). Preservation
  check = every baseline journey has a rendered outcome frame in the candidate at the same viewport, plus
  a mandatory human/independent judgement field `quality_regression: none | minor | major` with rationale.
  Nouns alone no longer satisfy preservation for UI nodes.
- **Prevents:** a redesign passing preservation while degrading density, hierarchy, findability.
- **Cost:** 1–2 days. **Risk:** medium — adds review effort per UI node; scale by R.
- **Class:** governance + orchestration.

### R-8 Artifact class is declared and gated (FAULT_FINDINGS §2)

- **Mechanism:** node `evidence_class` field (new); design-package template.
- **Change:** UI design nodes must declare `evidence_class ∈ {sketch, static_mock, isolated_html,
  react_prototype_in_repo, production}`. Operator-acceptance for a product redesign requires
  `react_prototype_in_repo` or higher; `isolated_html` can only satisfy `exploration` dimensions.
- **Prevents:** standalone HTML/CSS being treated as high-fidelity proof of a React product.
- **Cost:** 0.5 day. **Risk:** low. **Class:** configuration + governance.

### R-9 Guard defects (E-9)

- **Mechanism:** `eif_guard.py` path parser; timeouts.
- **Change:** (a) do not treat URL paths (`http://…/x`) as filesystem paths; (b) allow reading the agent's own
  terminal/transcript directory (declared by the host) as observation scope; (c) accept a declared
  **secondary root** for the EIF repo when the work item names it (this brief did); (d) raise or make
  configurable HOOK_TIMEOUT under concurrent tool calls; (e) `git diff`/`git status` naming protected paths is
  read-only and should be allowed.
- **Prevents:** inability to collect subagent audits, to write EIF remedies into the EIF repo, and spurious
  HOOK_INPUT_INVALID rejections.
- **Cost:** 1 day. **Risk:** low if (c) requires explicit work-item grant. **Class:** code + configuration.

## 2. What is *not* a defect

- The CONSULT ladder and `MODEL_CAPABILITIES.md` already say "other session and other model when
  available" — the rule existed; enforcement did not (R-2/R-3 are enforcement, not new policy).
- The runtime correctly refused `node.stage_note` without `expected_revision` and correctly enforced
  CONTROL_PLANE_PROTECTED on writes. Those are working controls.

## 3. What this run did about it (minimum lawful unblock)

- No EIF runtime file was modified by this run. The uncommitted modifications to `engine.py`, `store.py`,
  `independence.py`, `manifest.json`, `eif_guard.py` pre-date this run (E-7) and are left untouched and
  **uncommitted**; they are not part of any CIP commit from this run.
- CONSULT was executed with genuine model separation via the project's own mechanism (`claude -p --model
  opus`, `CONSULT_RESPONSE.md`), independent of the EIF runtime's declared-only check.
- All rendered claims in `rendered-verification.md` are marked UNVERIFIED (author-rendered) rather than PASS.

## 4. Sequencing

1. Commit the CIP design evidence (this run) — freezes `.eif/audit/NS_REDESIGN_R3_20260902/**` and the
   prototype source.
2. In the EIF repository, in a separate session: apply R-4, R-8 (cheap, configuration), then R-1/R-3/R-5
   (code), then R-6/R-7/R-9. Each with its own `governance.change` event.
3. Re-run N-0013 independence verification under the new runtime **from another session and model**; the
   result replaces nothing — it is appended.
