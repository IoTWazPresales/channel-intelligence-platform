'use client';

import { useCurrentUser } from '@/features/shell/useCurrentUser';

/**
 * Who may steward data (N-0086). Mirrors the API gates:
 * - steward writes on /imports, /mappings, /cst-steward, /product-master-gaps, /exceptions and
 *   /shipment-evidence need steward or admin (`require_roles(ADMIN, STEWARD)`);
 * - POST /imports/jobs and /process also admit planners for the CPOR templates below
 *   (`PLANNER_UPLOAD_TEMPLATES` in apps/api/app/api/v1/endpoints/imports.py).
 *
 * The API is the enforcement. This module only keeps the web honest: controls a role cannot use are
 * turned off with the reason, instead of failing with "Insufficient role" after a click.
 */

/** Import templates a planner may upload and process (keep in step with the API). */
export const PLANNER_IMPORT_TEMPLATES: ReadonlySet<string> = new Set(['cpor_historical_cases', 'cpor_payment_evidence']);

export type StewardWriteAccess = {
  /** True once the signed-in role is known. */
  known: boolean;
  /** Lower-case role, or null while unknown. */
  role: string | null;
  /** May use steward write controls. True while the role is unknown (the API still enforces). */
  allowed: boolean;
  /** Why the controls are off, for display; null when allowed. */
  reason: string | null;
};

function normalizeRole(role: string | null | undefined): string | null {
  const r = String(role ?? '').trim().toLowerCase();
  return r || null;
}

export function canStewardWrite(role: string | null | undefined): boolean {
  const r = normalizeRole(role);
  return r === 'admin' || r === 'steward';
}

export function stewardWriteBlockedReason(role: string | null | undefined): string {
  const r = normalizeRole(role) ?? 'a role without steward access';
  return (
    `You are signed in as ${r}. Stewarding data (uploading, mapping, resolving, ignoring, applying and ` +
    'clearing) needs the steward or admin role, so those controls are turned off here. You can still look ' +
    'around. Ask an admin to change your role if you need to steward data.'
  );
}

/** Pure form of {@link useStewardWriteAccess}, for tests and non-hook callers. */
export function stewardWriteAccess(role: string | null | undefined): StewardWriteAccess {
  const r = normalizeRole(role);
  if (r == null) return { known: false, role: null, allowed: true, reason: null };
  const allowed = canStewardWrite(r);
  return { known: true, role: r, allowed, reason: allowed ? null : stewardWriteBlockedReason(r) };
}

/** May this access start (or continue) an import of `templateSlug` in Import Center? */
export function canRunImportTemplate(access: StewardWriteAccess, templateSlug: string | null | undefined): boolean {
  if (access.allowed) return true;
  return access.role === 'planner' && templateSlug != null && PLANNER_IMPORT_TEMPLATES.has(templateSlug);
}

export function useStewardWriteAccess(): StewardWriteAccess {
  const { data: me } = useCurrentUser();
  return stewardWriteAccess(me?.role);
}
