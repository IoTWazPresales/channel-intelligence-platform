import { describe, expect, it } from 'vitest';

import {
  activeSpineContainerId,
  roleMayAccess,
  shellSpineContainers,
  shellUtilityNav,
} from '@/features/shell/spineNav';

describe('spine nav', () => {
  it('admin sees all six containers', () => {
    const ids = shellSpineContainers('admin').map((c) => c.id);
    expect(ids).toEqual(['brief', 'lineup', 'stock', 'settlement', 'response', 'steward']);
  });

  it('viewer sees brief and stock only from job containers', () => {
    const ids = shellSpineContainers('viewer').map((c) => c.id);
    expect(ids).toContain('brief');
    expect(ids).toContain('stock');
    expect(ids).not.toContain('steward');
    expect(ids).not.toContain('settlement');
  });

  it('activeSpineContainerId maps dashboard to brief and stock hub', () => {
    expect(activeSpineContainerId('/dashboard')).toBe('brief');
    expect(activeSpineContainerId('/brief')).toBe('brief');
    expect(activeSpineContainerId('/stock')).toBe('stock');
    expect(activeSpineContainerId('/sell-out')).toBe('stock');
  });

  it('utility nav admin-only for admin users entry', () => {
    expect(shellUtilityNav('viewer').some((u) => u.label === 'Admin')).toBe(false);
    expect(shellUtilityNav('admin').some((u) => u.label === 'Admin')).toBe(true);
  });

  it('roleMayAccess grants admin everything', () => {
    expect(roleMayAccess('admin', ['viewer'])).toBe(true);
    expect(roleMayAccess('viewer', ['admin'])).toBe(false);
  });
});
