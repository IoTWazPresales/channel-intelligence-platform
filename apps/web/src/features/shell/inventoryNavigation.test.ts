import { describe, expect, it } from 'vitest';

import { paletteHits } from './CommandPalette';
import { railNavGroups, shellNavGroups } from './navConfig';
import { matchNavLeaf, navPageChrome } from './navPageChrome';

describe('Inventory navigation', () => {
  it.each(['admin', 'steward', 'planner', 'viewer'])(
    'keeps Inventory and Hand-entered stock distinct in the rail and directory for %s',
    (role) => {
      for (const groups of [railNavGroups(role), shellNavGroups(role)]) {
        const stock = groups.find((group) => group.id === 'stock');
        expect(stock?.items.find((leaf) => leaf.href === '/inventory')).toMatchObject({
          label: 'Inventory',
          what: expect.stringContaining('weeks of cover'),
        });
        expect(stock?.items.find((leaf) => leaf.href === '/inventory/hand-entered')).toMatchObject({
          label: 'Hand-entered stock',
          what: expect.stringContaining('Hand-entered customer stock'),
        });
        expect(stock?.items.some((leaf) => leaf.label === 'Cover')).toBe(false);
      }
    },
  );

  it('finds the cover surface and the hand-entered grid separately in the command palette', () => {
    expect(paletteHits('admin', 'Inventory')).toContainEqual(expect.objectContaining({
      label: 'Inventory',
      href: '/inventory',
      meta: expect.stringContaining('weeks of cover'),
    }));
    expect(paletteHits('admin', 'Hand-entered stock')).toContainEqual(expect.objectContaining({
      label: 'Hand-entered stock',
      href: '/inventory/hand-entered',
      meta: expect.stringContaining('Hand-entered customer stock'),
    }));
  });

  it('gives Inventory its own title and breadcrumbs', () => {
    expect(navPageChrome('/inventory')).toEqual({
      title: 'Inventory',
      crumbs: [
        { label: 'Stock & Sell-through', href: '/stock' },
        { label: 'Inventory' },
      ],
    });
  });

  it('matches the hand-entered sibling and supports a breadcrumb back to Inventory', () => {
    expect(matchNavLeaf('/inventory/hand-entered')?.item).toMatchObject({
      label: 'Hand-entered stock',
      href: '/inventory/hand-entered',
    });
    expect(navPageChrome('/inventory/hand-entered').title).toBe('Hand-entered stock');
    expect(navPageChrome('/inventory', {
      extraCrumbs: [{ label: 'Hand-entered stock' }],
    })).toEqual({
      title: 'Hand-entered stock',
      crumbs: [
        { label: 'Stock & Sell-through', href: '/stock' },
        { label: 'Inventory', href: '/inventory' },
        { label: 'Hand-entered stock' },
      ],
    });
  });
});
