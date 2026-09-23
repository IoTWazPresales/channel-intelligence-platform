# GOV-001 routing reference (Volume 5)

## 5.2 Routing matrix

### Bug
Required:
- Discovery/Diagnosis
- relevant implementation specialist
- Test/QA
Optional:
- Security if trust boundary
- Data if integrity
- UX if user-visible

### New feature
Required:
- Discovery
- Product
- Architecture appropriate to scope
- implementation
- QA
Optional:
- UX, Data, Security, Market

### Refactor
Required:
- Discovery
- Maintainability/Architecture
- regression strategy
- implementation reviewer

No refactor may be justified solely by “cleaner.”

### Schema change
Required:
- Discovery
- Data Architect/DB Specialist
- owning backend specialist
- QA
- rollback/migration review

### Auth/security
Required:
- Discovery
- Security
- relevant architect/engineer
- QA
- independent Security Skeptic

### UI redesign
Required:
- Discovery
- Product
- UX
- UI (including rendered inspection when a UI exists)
- Accessibility
- frontend
- QA

### Project/module audit
Required:
- GOV-003 evidence baseline
- Product critique
- Architecture critique
- Product red team
- UX/visual/a11y when a renderable UI exists

Output is L1 proposals only. Implementation is a later envelope.

### Performance
Required:
- measured baseline
- Performance Specialist
- owning engineer
- verification benchmark

No speculative performance optimization.

## 5.4 Parallelization and state concurrency

Parallelize only independent investigations or implementations.

Good:
- security review and UX review of a stable proposal;
- database analysis and frontend analysis when interface is fixed;
- independent market comparison and repository discovery.

Bad:
- two agents editing the same core file without coordination;
- backend and frontend implementing an API before contract agreement;
- multiple agents rewriting persistent context.

Rules:
1. GOV-001 assigns a single writer for each canonical state file per run.
2. Parallel packages declare intended state writes before dispatch.
3. Overlapping declarations are a planning error and must be resolved first.
4. `DECISIONS`, `LESSONS`, `OPPORTUNITY_REGISTER`, and `RISK_REGISTER` are append-only.
5. `CURRENT.md` never uses last-writer-wins; specialists return proposed patches to its assigned writer.

## 5.5 Disagreement protocol

When specialists disagree, record:

- decision question;
- option A;
- option B;
- evidence for each;
- assumptions;
- impact;
- reversibility;
- experiment that could resolve it.

The orchestrator may decide if:
- within authority;
- evidence clearly favors one;
- decision is reversible.

Otherwise escalate.
