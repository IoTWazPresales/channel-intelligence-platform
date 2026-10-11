import { describe, expect, it } from 'vitest';
import type { LayoutItem } from 'react-grid-layout';

import { DASHBOARD_STACK_BELOW, layoutForWidth } from './DashboardGrid';

const saved: LayoutItem[] = [
  { i: '11', x: 0, y: 0, w: 4, h: 3 },
  { i: '12', x: 4, y: 0, w: 8, h: 8 },
];

describe('layoutForWidth', () => {
  it('keeps the saved 12-column layout on a wide canvas', () => {
    expect(layoutForWidth(saved, 1100)).toEqual(saved);
    expect(layoutForWidth(saved, DASHBOARD_STACK_BELOW)).toEqual(saved);
  });

  it('stacks widgets full-width below the phone breakpoint without changing their height', () => {
    expect(layoutForWidth(saved, 390)).toEqual([
      { i: '11', x: 0, y: 0, w: 12, h: 3 },
      { i: '12', x: 0, y: 3, w: 12, h: 8 },
    ]);
  });
});
