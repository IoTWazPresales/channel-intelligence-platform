# N-0065 discovery — product-line access (2026-10-07, run RUN-20261007-N0065-GOV)

Accepted rule: D-0056 (Warren 2026-10-07). Every signed-in screen filters to the user's assigned product lines; each line is Read or Read-and-edit; a non-admin with no assignment sees no product data; an ADMIN sees all lines.

AS-IS (dirty tree, uncommitted; migration 20261006_0024 already applied on cip):
- `apps/api/app/api/v1/router.py:29-44` — the router-level dependency reads `user_product_line_access` rows for the signed-in user and binds `request_product_lines` / `request_editable_product_lines`, then `apply_product_line_guc`. An admin gets the same treatment as everyone else, so an admin with no rows sees nothing. **This is the one behaviour to change.**
- `apps/api/app/core/product_line_scope.py` — contextvars; `None` leaves the database gate open (workers, forged test identities); empty = no lines; `widen_product_line_catalog` sets `*` so an admin can list lines to assign. Module docstring says "Admin does not bypass an empty assignment" — must change with the rule.
- `apps/api/app/api/deps.py:8-13` — `get_db` applies the scope to every request session.
- `apps/api/alembic/versions/20261006_0024_product_line_access.py:62-82,140-192` — row security on `dim_product` and product-keyed tables; `cip_product_id_visible/editable` already treat `*` as all lines and an unset setting as open.
- `apps/api/app/api/v1/endpoints/auth.py` — admin routes for product lines and assignment (`/auth/product-lines`, assignment form on Administration users).
- cip (CURRENT.md 2026-10-07): unset sees 18177 products, empty sees 0, `*` sees 18177; grant rows 0.

Gap to close: admins bind `*` for read and edit; docstring and any UI copy saying admins need an assignment are corrected; tests cover admin-with-no-rows sees all, non-admin-with-no-rows sees none, read-only line cannot be edited.
