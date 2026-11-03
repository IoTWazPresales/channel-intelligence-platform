# N-0100 extended — jobs, account coverage, My accounts

Definition only. Written 3 November 2026. No product code, no migration, no node stage change, no acceptance.

The original N-0100 criteria stay on the node. They are a duty split on promotion cases, a throttle on the public case-approval route, and the steward check on the older customer-merge endpoints. This document defines the 2 November scope extension only. It does not restate, replace, or close the original criteria.

Checked against `.eif/CONTEXT.md`, `.eif/DECISIONS.md`, and `.eif/JOURNEYS.yaml`. Conflicts are listed below and are not resolved here.

## Accepted, and what this document will not reopen

- D-0133 item 2 and D-0138, both accepted: a user has a job and covers customer accounts; dashboards, Brief, and Attention default to My accounts; the user can clear that filter; there is no database restriction.
- The node's existing criterion that the four system roles stay unless Warren decides otherwise.
- D-0056 / N-0065, accepted and already built: product-line assignment is a real restriction. A user with no assigned product line sees no product data. Admin `*` sees all product lines. My accounts does not replace that.

## What exists today

Roles in `apps/api/app/core/security.py`: `admin`, `steward`, `planner`, `viewer`. `require_roles` always allows `admin`.

Header aliases collapse other words onto those four. `product_manager` and `commercial_manager` become `planner`. `finance_reviewer` and `executive_viewer` become `viewer`. `data_steward` becomes `steward`. An unknown word becomes `viewer`.

`apps/api/app/models/iam.py`: `app_user` has `tenant_id`, `email`, `display_name`, `role`, `is_active`. There is no job column and no link from a user to customer accounts.

`user_product_line_access` (`apps/api/app/models/product_line_access.py`) is the product-line grant: tenant, user, product line, and whether that line may be edited. That table is a database restriction. My accounts must not be built the same way.

A dashboard starter gallery already exists (`account_overview` is one starter key). It is not bound to the signed-in user's customer accounts.

## Conflicts with the durable artifacts

- `.eif/CONTEXT.md` has no users, no jobs, and no account rule. Nothing in it contradicts this definition. The gap is that the durable context does not yet hold D-0138.
- `.eif/DECISIONS.md` records only D-0132, and records it as PROPOSED. The ledger records D-0132 as accepted. This definition does not confirm D-0132. My accounts is a clearable filter, not a recipient permission. Scheduled delivery stays on D-0132's product-line and tenant checks. Do not implement My accounts as that scope.
- `.eif/JOURNEYS.yaml` has one skeleton journey (`first-path`). It has no account-manager journey. The journeys below are specified here and are not in the catalog.
- The node title and the original criteria name people. Those names are not used in this definition. Copying them into a rule, a default, or a test would break the standing rule. They stay on the node until Warren changes that criterion.
- `docs/memory/CURRENT.md` says migration `20261102_0051` is not on `cip`. The 2 November deploy note says it was applied. Not checked against the database in this session, and not edited. This definition does not depend on `fact_upsert_key`.

## Job and role

A job is not a role. The five jobs are account manager, product manager, finance, country manager, and admin. The four roles stay `admin`, `steward`, `planner`, and `viewer`.

Store the job on the user, separate from `role`. Allowed values are those five, or empty. Do not write a job into `role`. The aliases above would hide it: a role value of product manager is stored and checked as planner.

Permission checks keep using the role. The job chooses the default filter and the first screen, once Warren accepts that matrix. A steward can also have a job. A user can have a role and no job.

Who may edit the job and the account assignment: the `admin` role. That is the same admin gate already used for user administration. It is not a new permission model.

## How a user is tied to customer accounts

One assignment row per tenant, user, and customer account. The customer must already exist in that tenant. The assignment does not create a customer, a store, or a distributor.

The row is data. It is not row-level security and not a policy. A query includes the account predicate only while the My accounts filter is on. Clearing the filter removes the predicate. The product-line restriction still applies either way.

An account the user is not assigned can still be opened after the filter is cleared, within the user's role and product lines.

## What each job sees first

Not accepted. Recorded as D-0141, proposed, on N-0100. Until Warren picks, do not ship a default-on filter.

Question: for each job, what is the first screen, and does My accounts start on?

Options:

1. Only an account manager, and only when that user has at least one assigned account, lands on the My accounts starter with the filter on. Every other job, a user with no job, the admin role, and an empty assignment land on the existing home (Brief) with the filter off. The filter control is still there.
2. Any job with a non-empty assignment, including admin, lands with the filter on. An empty assignment starts with the filter off.
3. A matrix Warren writes himself.

Evidence: D-0138 names account managers only. The node criterion names the three surfaces without naming a job. The five jobs have no screens of their own today. Product managers already have a product-line restriction that is not an account filter.

Assumptions: Brief remains the home for anyone who does not land on the starter. Empty assignment must not look like "this person is forbidden to see the company."

Impact: option 1 matches D-0138 and leaves finance, country manager, product manager, and admin on the company view. Option 2 hides other accounts from an admin until they clear the filter. Option 3 delays the filter until a matrix exists.

Reversibility: high. The filter is a query flag, not a stored permission. Changing the default does not rewrite facts.

Recommendation, not a decision: option 1. It is the only option that follows D-0138's wording. Warren picks.

Whatever is picked, a clear is not written to the database. It lasts for the sign-in session. A new session returns to the default. That is what "default" and "no database restriction" require.

## Where My accounts applies

Dashboards, Brief, Attention, and one My accounts starter dashboard built from the existing starter mechanism. The starter's account filter is bound to the signed-in user's assignment. It uses the same flag as the other three surfaces.

It does not apply to steward resolution, import apply, or scheduled delivery. Those keep their current rules.

## Acceptance criteria

These hold for any tenant and any customer accounts. No account name appears in a rule, a default, a fixture label, or a test description. Tests use generated accounts.

Accepted now, and safe to build before the first-screen decision:

1. A user has a job from the five, or no job, stored separately from `role`. Setting a job does not change `role` and does not change what `require_roles` allows.
2. An admin can assign and remove customer accounts for a user in the same tenant. The assignment does not create a master. A customer in another tenant is refused.
3. No row-security policy is added for the assignment. With the filter off, the account predicate is absent. Product-line restriction still applies.
4. No customer, distributor, retailer, store, product, or vendor name is introduced in code, config, or tests for this work.

Waiting on the first-screen decision:

5. The chosen job starts on the screen that decision names, with My accounts on or off as that decision says.
6. When the filter is on, dashboards, Brief, Attention, and the starter show only the signed-in user's assigned accounts. Clearing it shows the wider set the role and product lines already allow, and the next session returns to the default.
7. A user with an empty assignment does not see an empty company unless the decision says so.
8. The starter is created from the existing builder, and its account filter is the same flag.

Original N-0100 criteria (duty split, case-approval throttle, merge steward check) are unchanged and are not criteria of this extension.

## Journeys

Not in `.eif/JOURNEYS.yaml`. Specified for the render pass:

1. An account manager with two assigned accounts opens Brief, sees those two, clears My accounts, and sees further accounts that their product lines allow. A new sign-in returns to the default. They never see another tenant.
2. A user with no assigned accounts opens Brief and can tell that the filter is off because nothing is assigned, once the decision says that is the behaviour.
3. An admin edits another user's job and accounts, signs in as that user, and sees the default the decision names. The admin's own role is still admin.
4. Keyboard: the filter control and Clear are reachable without a pointer. The starter is reachable from the dashboard home.

## Risks

- Building the filter as row-level security would contradict D-0138 and would hide accounts even after Clear.
- Storing the job in `role` would collapse product manager to planner and finance to viewer through the existing aliases.
- An empty assignment with the filter forced on shows a blank company and looks like a restriction.
- The original node text names people. A later session that "implements N-0100" can copy those names into rules. This extension must not.
- Product-line restriction and My accounts compose. A test that only checks accounts can pass while product lines still hide the rows, or the reverse.
- D-0132 must not be edited or treated as confirmed by this work.

## Migration

One migration, not run here, and not authorised by this definition:

- Nullable job on `app_user`, constrained to the five values or null. No new value in the role enum.
- An assignment table: tenant, user, customer, unique on that triple, foreign keys to `tenant`, `app_user`, and the customer master. No row-security policy.
- No change to `user_product_line_access`.

Apply only after Warren's usual migration go. The filter units do not need this migration to be designed; they need it to be applied before they are exercised on `cip`.

## Build order

Each unit is sized for one implementation session. Do not start a unit whose decision is still proposed.

1. Job column, assignment table, admin editor, and the tests in criteria 1–4. No filter and no starter. Does not need the first-screen decision. The node blocker below is about the filter, not about this unit. The engine still marks the whole node blocked; Warren says if this unit may start while the blocker is open.
2. After the first-screen decision: the shared filter on dashboard queries. Clear control. Session-only. Tests for the chosen matrix.
3. Same decision: Brief and Attention use that same flag. One sitting if unit 2 stayed in the dashboard query layer; otherwise its own sitting.
4. My accounts starter bound to the signed-in user, using the existing starter path.
5. Renders listed below, after the surfaces exist.

## Tests and renders

Tests, with generated users and generated accounts, rolled back:

- Job set, role byte-for-byte unchanged, `require_roles` unchanged.
- Assignment insert refuses a customer in another tenant and does not insert a customer.
- Filter off: the account predicate is not in the query. Filter on: only assigned account ids. Product-line predicate still present for a non-admin.
- No policy migration in the revision under test.
- Alias check: a role string that the aliases already map still maps the same way after the job column exists.

Renders, after the filter units exist, light and dark, 1280 and 390:

- Brief, Attention, a dashboard, and the starter, with the filter on and after Clear.
- Empty assignment, in the state the decision names.
- Admin assignment editor: set a job, add an account, remove it.

Not a render of production data. Not a claim that N-0100 is accepted.

## Choices left for Warren

1. D-0141. First screen and whether My accounts starts on, for each job, including a user with no job and a user with an empty assignment. Proposed. Blocks the filter and the starter. Does not by itself block the assignment table.
2. D-0132 stays unconfirmed, on purpose.
3. Whether `20261102_0051` is on `cip`. This definition does not need an answer.

M5c (mapping memory and aliases) is in `STORE_DC_MODULE_DEFINITION.md`. It is not part of this job work and does not block these units.
