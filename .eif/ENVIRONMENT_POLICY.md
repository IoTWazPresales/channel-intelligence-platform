---
eif: environment-policy
version: 0.3
status: proposed
last_updated:
owner:
review_after: 30d
project_id:
policy_id:
---

# Environment / Release Policy

## Environments

### Development
- Allowed authority:
- Named mechanisms:

### Staging
- Allowed authority:
- Named release mechanism:

### Production
- Allowed authority: L4
- L5 enabled: false
- Named release mechanism:

## Required controls
- Protected branch:
- Immutable audit log:
- Automated pre-release checks:
- Rollback/roll-forward proof:
- Post-release verification:
- Least-privilege credential scope:

## Release window

## Rollback triggers

## Hard stop conditions

## Release ladder (REL)

- Active rung: REL-0 (local/workspace). Programme file-tool deny may be ENFORCED after same-mode probe. Child-process ledger immutability: UNAVAILABLE unless a later probe proves containment.
- REL-1 (named CI/CD + protected branch + independent verify): architecture only; not granted by this template.
