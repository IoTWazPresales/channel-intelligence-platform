import { describe, expect, it } from 'vitest';

import { filterNavGroupsForRole, roleMayAccess, shellNavGroups } from '@/features/shell/navConfig';

describe('nav role gating', () => {
  it('admin sees Users and steward audit', () => {
    const groups = shellNavGroups('admin');
    const hrefs = groups.flatMap((g) => g.items.map((i) => i.href));
    expect(hrefs).toContain('/admin/users');
    expect(hrefs).toContain('/admin/steward-audit');
    expect(hrefs).toContain('/admin/ops');
    expect(hrefs).toContain('/commercial-planner');
    expect(hrefs).toContain('/admin/imports');
  });

  it('viewer sees overview/channel but not admin or steward writes', () => {
    const groups = shellNavGroups('viewer');
    const hrefs = groups.flatMap((g) => g.items.map((i) => i.href));
    expect(hrefs).toContain('/dashboard');
    expect(hrefs).toContain('/sell-out');
    expect(hrefs).not.toContain('/admin/users');
    expect(hrefs).not.toContain('/admin/imports');
    expect(hrefs).not.toContain('/commercial-planner');
  });

  it('planner sees commercial but not Users', () => {
    const groups = shellNavGroups('planner');
    const hrefs = groups.flatMap((g) => g.items.map((i) => i.href));
    expect(hrefs).toContain('/commercial-planner');
    expect(hrefs).not.toContain('/admin/users');
    expect(hrefs).not.toContain('/admin/imports');
  });

  it('steward sees imports/master and steward audit but not Users', () => {
    const groups = shellNavGroups('steward');
    const hrefs = groups.flatMap((g) => g.items.map((i) => i.href));
    expect(hrefs).toContain('/admin/imports');
    expect(hrefs).toContain('/admin/products');
    expect(hrefs).toContain('/admin/steward-audit');
    expect(hrefs).toContain('/admin/ops');
    expect(hrefs).not.toContain('/commercial-planner');
    expect(hrefs).not.toContain('/admin/users');
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
});
