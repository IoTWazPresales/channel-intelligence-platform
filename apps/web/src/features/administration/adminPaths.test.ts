import { describe, expect, it } from 'vitest';

import { adminLensFromPath, adminWorkflowHref } from './adminPaths';

describe('adminPaths', () => {
  it('maps production Administration routes onto hub and relocated leaves', () => {
    expect(adminLensFromPath('/admin/users')).toBe('hub');
    expect(adminLensFromPath('/admin/users/list')).toBe('users');
    expect(adminLensFromPath('/admin/ops')).toBe('ops');
    expect(adminLensFromPath('/admin/sql-viewer')).toBe('sql');
    expect(adminLensFromPath('/settings')).toBe('settings');
    expect(adminLensFromPath('/admin/imports')).toBe('hub');
  });

  it('relocates Users & roles href without changing other leaves', () => {
    expect(adminWorkflowHref('/admin/users')).toBe('/admin/users/list');
    expect(adminWorkflowHref('/admin/ops')).toBe('/admin/ops');
    expect(adminWorkflowHref('/settings')).toBe('/settings');
  });
});
