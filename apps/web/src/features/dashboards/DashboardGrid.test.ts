import { describe, expect, it } from 'vitest';
import type { LayoutItem } from 'react-grid-layout';

import { DASHBOARD_STACK_BELOW, layoutForWidth, nudgeLayout } from './DashboardGrid';

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

describe('nudgeLayout', () => {
  const items = [
    { id: 11, layout: { x: 0, y: 0, w: 4, h: 4 } },
    { id: 12, layout: { x: 4, y: 0, w: 8, h: 8 } },
  ];

  it('moves a widget one cell and refuses to leave the grid', () => {
    expect(nudgeLayout(items, 11, 'right')?.[0].layout).toEqual({ x: 1, y: 8, w: 4, h: 4 });
    expect(nudgeLayout(items, 11, 'left')).toBeNull();
  });

  it('resizes with the shift actions and keeps the minimum size', () => {
    expect(nudgeLayout(items, 11, 'wider')?.[0].layout.w).toBe(5);
    expect(nudgeLayout(items, 11, 'narrower')?.[0].layout.w).toBe(3);
    expect(nudgeLayout([{ id: 11, layout: { x: 0, y: 0, w: 3, h: 4 } }], 11, 'narrower')).toBeNull();
  });
});
