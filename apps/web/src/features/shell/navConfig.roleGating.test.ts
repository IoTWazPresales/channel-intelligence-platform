import { describe, expect, it } from 'vitest';

import {
  filterNavGroupsForRole,
  inRail,
  leafStatus,
  railNavGroups,
  roleMayAccess,
  shellNavGroups,
} from '@/features/shell/navConfig';

function hrefsFor(role: string): string[] {
  return shellNavGroups(role).flatMap((g) => g.items.map((i) => i.href));
}

function labelsFor(role: string): string[] {
  return shellNavGroups(role).map((g) => g.label);
}

describe('nav role gating (D-0008 capability domains)', () => {
  it('admin sees Administration, planner, and stewardship leaves', () => {
    const hrefs = hrefsFor('admin');
    expect(labelsFor('admin')).toEqual([
      'Overview',
      'Stock & Sell-through',
      'Supply & Inbound',
      'Planning',
      'Promotions & Funding',
      'Market & Listings',
      'Data & Stewardship',
      'Administration',
    ]);
    expect(hrefs).toContain('/admin/users');
    expect(hrefs).toContain('/admin/sql-viewer');
    expect(hrefs).toContain('/admin/steward-audit');
    expect(hrefs).toContain('/admin/ops');
    expect(hrefs).toContain('/commercial-planner');
    expect(hrefs).toContain('/admin/imports');
  });

  it('viewer sees overview and market evidence, not admin or planner writes', () => {
    const hrefs = hrefsFor('viewer');
    expect(hrefs).toContain('/brief');
    expect(hrefs).toContain('/reports');
    expect(hrefs).toContain('/dashboards');
    expect(hrefs).toContain('/inbox');
    expect(hrefs).toContain('/channel-intelligence');
    expect(hrefs).toContain('/listing-capture?tab=registry');
    expect(hrefs).not.toContain('/dashboard');
    expect(hrefs).not.toContain('/sell-out');
    expect(hrefs).not.toContain('/admin/users');
    expect(hrefs).not.toContain('/admin/sql-viewer');
    expect(hrefs).not.toContain('/admin/imports');
    expect(hrefs).not.toContain('/commercial-planner');
    expect(hrefs).not.toContain('/lineup');
    expect(labelsFor('viewer')).not.toContain('Administration');
    expect(labelsFor('viewer')).not.toContain('Data & Stewardship');
    expect(labelsFor('viewer')).not.toContain('Planning');
    expect(labelsFor('viewer')).not.toContain('Promotions & Funding');
  });

  it('planner sees commercial and funding, not Users or Import Center', () => {
    const hrefs = hrefsFor('planner');
    expect(hrefs).toContain('/commercial-planner');
    expect(hrefs).toContain('/commercial-planner/cpor-cases');
    expect(hrefs).toContain('/lineup');
    expect(hrefs).not.toContain('/admin/users');
    expect(hrefs).not.toContain('/admin/sql-viewer');
    expect(hrefs).not.toContain('/admin/imports');
    expect(labelsFor('planner')).toContain('Promotions & Funding');
    expect(labelsFor('planner')).not.toContain('Data & Stewardship');
    expect(labelsFor('planner')).not.toContain('Administration');
  });

  it('steward sees imports/master and steward audit but not Users or planner', () => {
    const hrefs = hrefsFor('steward');
    expect(hrefs).toContain('/admin/imports');
    expect(hrefs).toContain('/admin/products');
    expect(hrefs).toContain('/admin/steward-audit');
    expect(hrefs).toContain('/admin/ops');
    expect(hrefs).toContain('/admin/mappings');
    expect(hrefs).not.toContain('/admin/sql-viewer');
    expect(hrefs).not.toContain('/commercial-planner');
    expect(hrefs).not.toContain('/admin/users');
    expect(labelsFor('steward')).toContain('Data & Stewardship');
    expect(labelsFor('steward')).not.toContain('Planning');
    expect(labelsFor('steward')).not.toContain('Promotions & Funding');
  });

  it('roleMayAccess grants admin everything', () => {
    expect(roleMayAccess('admin', ['viewer'])).toBe(true);
    expect(roleMayAccess('viewer', ['admin'])).toBe(false);
  });

  it('filterNavGroupsForRole drops empty groups', () => {
    const filtered = filterNavGroupsForRole(
      [{ id: 'x', label: 'X', items: [{ label: 'A', href: '/a', roles: ['admin'] }] }],
      'viewer'
    );
    expect(filtered).toEqual([]);
  });

  it('rail drops substrate and planned leaves (directory still has them)', () => {
    const directory = shellNavGroups('admin');
    const rail = railNavGroups('admin');
    const dirHrefs = directory.flatMap((g) => g.items.map((i) => i.href));
    const railHrefs = rail.flatMap((g) => g.items.map((i) => i.href));
    expect(dirHrefs).toContain('/budgets');
    expect(dirHrefs).toContain('/competition');
    expect(railHrefs).not.toContain('/budgets');
    expect(railHrefs).not.toContain('/competition');
    for (const g of rail) {
      for (const item of g.items) {
        expect(inRail(item)).toBe(true);
        expect(['live', 'partial']).toContain(leafStatus(item));
      }
    }
  });
});
