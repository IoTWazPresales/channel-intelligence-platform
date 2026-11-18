import { describe, expect, it } from 'vitest';

import { groupAgedLines, type AgedLine } from './agedStockGroups';

const line = (over: Partial<AgedLine>): AgedLine => ({
  customer_id: 1,
  customer_name: 'Customer A',
  product_id: 9,
  product_name: 'Product X',
  site_label: 'North',
  stock_on_hand: 4,
  slow: true,
  unsold: false,
  suggestions: ['promote', 'move', 'return'],
  executed_actions: [],
  ...over,
});

describe('groupAgedLines (Final wave c)', () => {
  it('folds the sites of one product into one line with the summed stock and both reasons', () => {
    const groups = groupAgedLines([
      line({ site_label: 'North', stock_on_hand: 4 }),
      line({ site_label: 'South', stock_on_hand: 2.5, slow: false, unsold: true }),
      line({ product_id: 10, product_name: 'Product Y', site_label: 'North', stock_on_hand: 1 }),
    ]);
    expect(groups.map((g) => [g.key, g.sites.length, g.stock_on_hand, g.reasons])).toEqual([
      ['1-9', 2, 6.5, ['slow', 'unsold']],
      ['1-10', 1, 1, ['slow']],
    ]);
  });

  it('keeps two customers with the same product apart', () => {
    const groups = groupAgedLines([
      line({ customer_id: 1 }),
      line({ customer_id: 2, customer_name: 'Customer B' }),
    ]);
    expect(groups.map((g) => g.key)).toEqual(['1-9', '2-9']);
  });

  it('drops a repeated site whose label differs only in case or spacing', () => {
    const groups = groupAgedLines([
      line({ site_label: 'North Mall' }),
      line({ site_label: ' north  mall ' }),
    ]);
    expect(groups).toHaveLength(1);
    expect(groups[0].sites).toHaveLength(1);
    expect(groups[0].stock_on_hand).toBe(4);
  });

  it('reports no stock figure when no site reports one', () => {
    const groups = groupAgedLines([line({ stock_on_hand: null, site_label: null })]);
    expect(groups[0].stock_on_hand).toBeNull();
  });
});

describe('truncated lists (Codex review of PR #114, B1)', () => {
  const line = (customer_id: number, product_id: number, site: string, soh: number): AgedLine => ({
    customer_id,
    product_id,
    site_label: site,
    stock_on_hand: soh,
    slow: true,
  });

  it('marks only the last customer\'s groups incomplete when the API cut the list', () => {
    const lines = [line(1, 10, 'Site A', 5), line(2, 20, 'Site A', 1), line(2, 20, 'Site B', 1)];
    const groups = groupAgedLines(lines, true);
    expect(groups.find((g) => g.customer_id === 1)?.incomplete).toBe(false);
    const cut = groups.find((g) => g.customer_id === 2);
    expect(cut?.incomplete).toBe(true);
    expect(cut?.sites).toHaveLength(2);
    expect(cut?.stock_on_hand).toBe(2);
  });

  it('marks nothing incomplete when the list is whole', () => {
    const groups = groupAgedLines([line(1, 10, 'Site A', 5), line(2, 20, 'Site A', 1)]);
    expect(groups.every((g) => !g.incomplete)).toBe(true);
  });
});
