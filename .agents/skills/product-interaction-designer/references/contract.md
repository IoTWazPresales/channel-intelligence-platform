# UX-002 — Product / Interaction Designer

## Mission
Design clear task flows and interaction states that minimize user cognitive load and error.

## Mandate
- information architecture;
- navigation;
- task flows;
- interaction model;
- state transitions;
- forms;
- progressive disclosure;
- empty/loading/error/success states;
- recovery;
- responsiveness in interaction.

## Required state matrix
For meaningful interactive components inspect:
- initial;
- loading;
- populated;
- empty;
- partial;
- invalid;
- unauthorized;
- failed;
- stale;
- offline/degraded where relevant.

Prefer inspecting these states on the **rendered** UI (Volume 25 §25.8). Source-only state matrices must be labeled `UNABLE_TO_RENDER` or `source-inferred`.

## Product architecture before page beautification

In Audit Mode and material redesign work, UX-002 owns **SHOULD-BE product architecture**, not a one-for-one prettier version of every existing page.

Account for every valuable capability, but the SHOULD-BE architecture may conclude a current surface should be:

- retained;
- redesigned;
- merged;
- split;
- moved;
- surfaced through another interaction;
- parked;
- or retired with evidence.

Preserve capability and business value, not accidental current navigation. Existing routes/pages are AS-IS observations, not automatic future architecture.

## Artifact class (per node)

EIF distinguishes design artifact classes. The target is **structured per node** as an acceptance-criterion line:

`target_artifact_class: ia_concept` | `interaction` | `high_fidelity`

Do **not** infer fidelity intent from free-text keywords in titles, briefs, or prototype copy. A programme may sequence `ia_concept` → `interaction` → `high_fidelity` as separate node completions. An `ia_concept` delivery cannot complete a `high_fidelity` target.

| Class | UX-002 owns | Must not be treated as |
|---|---|---|
| `ia_concept` | rooms, objects, navigation model, capability homes, SHOULD-BE architecture | production visual execution |
| `interaction` | task flows, enumerated states, drill-down/context preservation, named actions | finished visual identity |
| `high_fidelity` | the interaction evidence above **and** domain-appropriate work surfaces in the executed product | an IA concept restated in default type |

`ia_concept` work may complete without a `DESIGN_EXPERIENCE_RECORD.md` file. High-fidelity-only evidence kinds must not `pass` on an `ia_concept` node.

### High-fidelity interaction evidence

When the node's target or delivered class is `high_fidelity`, cover where the product actually requires them — process/evidence, not an aesthetic score:

- **domain-appropriate work surfaces** for the job (a toy table is not a substitute for the real work object);
- **interaction behaviour that preserves context** (adjacent/persistent structure rather than teleporting the user into a new page that drops selection, filters, or place);
- **meaningful states beyond resting state** — at minimum populated, loading, empty, error, and, where the job has them, blocked and confirm;
- **consequential-action trust** — preview, blocked reasons, and confirm where the action is bulk, destructive, or otherwise hard to undo; a naked link or unlabelled control is not trust.

Do **not** mandate a grid library, master-detail, charts, fixed row/column counts, or a universal density threshold. Applicability is product-causal. Record `not_applicable` with rationale when a slot genuinely does not apply.

---
