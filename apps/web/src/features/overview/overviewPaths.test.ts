import { describe, expect, it } from 'vitest';

import { overviewAttentionFirst, overviewLeafFromPath } from './overviewPaths';

describe('overviewPaths', () => {
  it('maps production Overview leaves', () => {
    expect(overviewLeafFromPath('/brief')).toBe('hub');
    expect(overviewLeafFromPath('/dashboards')).toBe('dashboard');
    expect(overviewLeafFromPath('/reports')).toBe('reports');
    expect(overviewLeafFromPath('/inbox')).toBe('inbox');
  });

  it('puts Attention first only on mobile with zone=attention', () => {
    expect(overviewAttentionFirst(true, 'attention')).toBe(true);
    expect(overviewAttentionFirst(false, 'attention')).toBe(false);
    expect(overviewAttentionFirst(true, null)).toBe(false);
  });
});
