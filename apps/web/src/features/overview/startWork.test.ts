import { describe, expect, it } from 'vitest';

import { START_VERBS, startVerbsForRole } from './startWork';

describe('startVerbsForRole', () => {
  it('admin sees every verb, including both lineup create and cases', () => {
    const ids = startVerbsForRole('admin').map((v) => v.id);
    expect(ids).toEqual(START_VERBS.map((v) => v.id));
    expect(ids).toContain('create-lineup');
    expect(ids).toContain('open-lineup');
  });

  it('steward can import and queue, not settle or open lineup cases', () => {
    const ids = startVerbsForRole('steward').map((v) => v.id);
    expect(ids).toEqual(['create-lineup', 'import-sell-through', 'import-shipping', 'steward-queue']);
  });

  it('planner can open cases, create a promotion plan, and settle, not Import Center', () => {
    const ids = startVerbsForRole('planner').map((v) => v.id);
    expect(ids).toEqual(['open-lineup', 'create-promo-plan', 'settle-case']);
  });

  it('viewer has no start verbs', () => {
    expect(startVerbsForRole('viewer')).toEqual([]);
  });

  it('every verb points at an existing work screen, not Attention', () => {
    for (const v of START_VERBS) {
      expect(v.href.startsWith('/brief')).toBe(false);
      expect(v.href.includes('zone=attention')).toBe(false);
    }
    expect(START_VERBS.find((v) => v.id === 'create-lineup')?.href).toBe('/admin/imports?unified=1');
    expect(START_VERBS.find((v) => v.id === 'create-lineup')?.label).toBe('Import a lineup');
    expect(START_VERBS.find((v) => v.id === 'import-sell-through')?.href).toBe(
      '/admin/imports?template=customer_sell_through',
    );
    expect(START_VERBS.find((v) => v.id === 'import-shipping')?.href).toBe(
      '/admin/imports?template=inbound_shipments',
    );
    expect(START_VERBS.find((v) => v.id === 'create-promo-plan')?.href).toBe('/promotions?propose=1');
    expect(START_VERBS.find((v) => v.id === 'settle-case')?.href).toBe('/commercial-planner/cpor-cases');
    expect(START_VERBS.find((v) => v.id === 'steward-queue')?.href).toBe('/admin/mappings');
    expect(START_VERBS.find((v) => v.id === 'steward-queue')?.label).toBe('Resolve unmatched tokens');
    expect(START_VERBS.find((v) => v.id === 'steward-queue')?.what).toMatch(/Unmatched tokens from imports/);
    expect(START_VERBS.find((v) => v.id === 'open-lineup')?.label).toBe('Review lineup cases');
    expect(START_VERBS.find((v) => v.id === 'create-promo-plan')?.label).toBe('Propose a promotion');
    expect(START_VERBS.find((v) => v.id === 'settle-case')?.label).toBe('Settle a funding case');
    expect(START_VERBS.find((v) => v.id === 'create-lineup')?.group).toBe('plan');
    expect(START_VERBS.find((v) => v.id === 'import-sell-through')?.group).toBe('data');
    expect(START_VERBS.find((v) => v.id === 'settle-case')?.group).toBe('funding');
  });
});
