import { describe, expect, it } from 'vitest';

import {
  PLANNER_IMPORT_TEMPLATES,
  canRunImportTemplate,
  canStewardWrite,
  stewardWriteAccess,
  stewardWriteBlockedReason,
} from './stewardAccess';

describe('canStewardWrite (N-0086, mirrors require_roles(ADMIN, STEWARD))', () => {
  it.each([
    ['admin', true],
    ['steward', true],
    ['Steward', true],
    ['planner', false],
    ['viewer', false],
    ['', false],
    [null, false],
    [undefined, false],
  ])('%s -> %s', (role, expected) => {
    expect(canStewardWrite(role as string | null | undefined)).toBe(expected);
  });
});

describe('stewardWriteAccess', () => {
  it('stays allowed while the role is unknown (the API still enforces)', () => {
    expect(stewardWriteAccess(undefined)).toEqual({ known: false, role: null, allowed: true, reason: null });
  });

  it('allows stewards and admins without a reason', () => {
    expect(stewardWriteAccess('steward')).toMatchObject({ known: true, allowed: true, reason: null });
    expect(stewardWriteAccess('admin')).toMatchObject({ known: true, allowed: true, reason: null });
  });

  it.each(['planner', 'viewer'])('blocks %s and names the role and the roles that may', (role) => {
    const a = stewardWriteAccess(role);
    expect(a).toMatchObject({ known: true, role, allowed: false });
    expect(a.reason).toBe(stewardWriteBlockedReason(role));
    expect(a.reason).toContain(`signed in as ${role}`);
    expect(a.reason).toContain('steward or admin');
  });
});

describe('canRunImportTemplate (mirrors PLANNER_UPLOAD_TEMPLATES in imports.py)', () => {
  it('lets planners run only the CPOR templates', () => {
    const planner = stewardWriteAccess('planner');
    expect([...PLANNER_IMPORT_TEMPLATES].sort()).toEqual(['cpor_historical_cases', 'cpor_payment_evidence']);
    for (const slug of PLANNER_IMPORT_TEMPLATES) expect(canRunImportTemplate(planner, slug)).toBe(true);
    for (const slug of ['distributor_inventory', 'customer_sell_through', 'inbound_shipments', 'cpor_claim_evidence', null]) {
      expect(canRunImportTemplate(planner, slug)).toBe(false);
    }
  });

  it('never lets viewers run a template, and always lets stewards', () => {
    expect(canRunImportTemplate(stewardWriteAccess('viewer'), 'cpor_payment_evidence')).toBe(false);
    expect(canRunImportTemplate(stewardWriteAccess('steward'), 'distributor_inventory')).toBe(true);
    expect(canRunImportTemplate(stewardWriteAccess('steward'), null)).toBe(true);
  });
});
