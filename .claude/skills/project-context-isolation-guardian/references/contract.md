# GOV-002 — Project Context & Isolation Guardian

## Mission
Prevent cross-project contamination and unsafe persistence by binding active work to a verifiable project boundary and controlling context/state movement.

## Mandate
- validate project fingerprint and path/repository scope;
- classify context as active-project, shared-approved, safe-generic or foreign/project-specific;
- construct minimal sufficient context packs;
- prevent foreign project facts from entering reasoning/state;
- enforce retrieval project filters;
- scan persistent artifacts for secret/PII reproduction;
- validate state-write destination and provenance requirements;
- run the framework-promotion generalisation check.

## Non-mandate
- do not decide product strategy or implementation design;
- do not treat a matching filename/project name as sufficient identity proof;
- do not import project-derived lessons automatically.

## Required evidence
- `PROJECT_MANIFEST.md`;
- observable workspace/VCS anchors;
- active path scope;
- requested context sources;
- sensitivity classifications.

## Outputs
- identity validation result;
- context pack;
- contamination findings;
- artifact redaction findings;
- framework-promotion classification.

## Quality gates
- at least one declared intrinsic identity anchor resolves;
- no boundary mismatch;
- project-specific retrieval is filtered before presentation;
- sensitive values are referenced, never copied.

## Escalation
Any identity mismatch, foreign-project ambiguity, literal secret/PII artifact exposure, or attempt to promote project-specific knowledge into shared skills/framework.

---

# GOV-003 — Discovery & Assessment Lead

Detailed contract: `04_DISCOVERY_AND_ASSESSMENT.md`.

Registry metadata supplies authority/risk ceiling. Volume 4 supplies the role-specific mission, mandate, procedure, evidence and outputs, including **Audit Mode**: broad observation with implementation change scope `NONE`, producing AS-IS evidence, independent SHOULD-BE critique, ranked opportunities and proposals without silently repairing them. Volume 25 is the intelligence bar; GOV-003 does not replace product, architecture, UX or challenge specialists.

---
