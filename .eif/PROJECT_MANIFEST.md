---
eif: project-manifest
version: 0.3
status: bootstrap
last_updated: null
owner: null
review_after: 90d
project_id: channel-intelligence-platform
project_name: channel-intelligence-platform
state_root: .eif
lifecycle: brownfield
sensitivity: unknown
identity:
  vcs_root: C:/Users/warren_eliason/channel-intelligence-platform
  remotes:
  - https://github.com/IoTWazPresales/channel-intelligence-platform.git
  root_commit: 8f7f1b53e3555dd3010244c7fe8b398ecb881548
  path_scopes:
  - '**'
  additional_repositories: []
policies:
  autonomy: AUTONOMY_POLICY.md
  environment: ENVIRONMENT_POLICY.md
protected_paths:
- vendor/**
- '**/vendor/**'
- dist/**
- build/**
- '**/generated/**'
sensitive_read_paths:
- .env
- .env.*
- '**/*.pem'
- '**/*secret*'
- '**/*credential*'
---

> **Artifact safety:** This file anchors project identity and is expected to be broadly readable. Never store secret values, credentials, tokens or customer PII here.

# Project Manifest

The YAML front matter is the **authoritative machine-readable identity block**. Do not duplicate `project_id` or `project_name` elsewhere in this file as a competing source of truth.

## Product
- Primary product/domain:
- Target users:
- Buyer(s):
- Core problem:
- Product promise:
- Primary success measures:

## Scope
- System/project boundary:
- Default observation boundary:
- Default implementation/change boundary:
- Explicitly out of scope:
- Shared services/assets:
- Monorepo/shared-path notes:

> Observation permission never implies change permission. Work items narrow both boundaries further.

## Authoritative sources
- Product/business truth:
- Architecture/technical truth:
- Operations/runtime truth:
- Security/privacy policy:

## Protected paths

### Never modify directly
- Generated code (change generator/source instead):
- Vendored dependencies:
- Applied/immutable migrations where project policy declares them immutable:

### Modify only through named tooling or explicit grant
- Lockfiles (package-manager/tooling only):
- Infrastructure/security configuration:
- Other teams' CODEOWNERS territory:
- Shared libraries/platform surfaces:

## Technology
- Languages:
- Frameworks:
- Runtime:
- Persistence:
- Infrastructure:
- Build/test tooling:

## Environments
- Local/dev:
- Test/staging:
- Production:
- Environment policy reference:

## Isolation
- Allowed project-local context sources:
- Approved shared generic sources:
- Explicit cross-project exceptions:
- Retrieval/index boundary:

## Current constraints
- Time/business constraints:
- Compliance/security constraints:
- Compatibility constraints:
- Cost constraints:

## Bootstrap verification
- Fingerprint verified by:
- Verification evidence:
- Date:
- Unverified fields:
