import { describe, expect, it } from 'vitest';

import {
  computeDsiContinueGateKey,
  dsiContinueToApplyAllowed,
  dsiDataQualityBlockingRows,
  dsiDateSatisfiedBySnapshotStamp,
  dsiGateFromMapping,
  dsiGateFromNestedMapping,
  dsiHumanFixableBlockingRows,
  dsiMappingRequiredGroupsFromDraft,
  fanOutDsiLayoutDraft,
  groupDsiSheetKeys,
  dsiSelectValue,
  dsiStewardMapBlockingRows,
  dsiTargetDescription,
  dsiTargetLabel,
  formatDsiBlockerSummaryLine,
  hydrateDsiNestedMapDraft,
  isNestedDsiFieldMapping,
  parseDistributorSiSummaryFromRows,
  stableFieldMappingJson,
} from './dsiStepUtils';

describe('dsiStepUtils', () => {
  it('uses friendly labels for key DSI targets', () => {
    expect(dsiTargetLabel('product_identifier')).toMatch(/SKU/i);
    expect(dsiTargetLabel('product_identifier')).toMatch(/part/i);
    expect(dsiTargetLabel('distributor_token')).toBe('Distributor');
    expect(dsiTargetLabel('channel_key_token')).toMatch(/Channel/i);
    expect(dsiTargetLabel('dealer_group_token')).toBe('Customer account');
    expect(dsiTargetLabel('customer_dealer_token')).toBe('Source customer name');
  });

  it('dsiTargetDescription clarifies customer account vs source name', () => {
    expect(dsiTargetDescription('dealer_group_token')).toMatch(/reporting/i);
    expect(dsiTargetDescription('dealer_group_token')).toMatch(/matching/i);
    expect(dsiTargetDescription('dealer_group_token')).toMatch(/roll up/i);
    expect(dsiTargetDescription('dealer_group_token')).toMatch(/Dealer Name Group/i);
    expect(dsiTargetDescription('customer_dealer_token')).toMatch(/alias/i);
    expect(dsiTargetDescription('customer_dealer_token')).toMatch(/evidence/i);
    expect(dsiTargetDescription('customer_dealer_token')).toMatch(/Customer name/i);
    expect(dsiTargetDescription('distributor_token')).toBeUndefined();
  });

  it('dsiSelectValue never returns unknown canonical targets', () => {
    const canon = new Set(['distributor_token', 'channel_key_token']);
    expect(dsiSelectValue('channel_code', canon)).toBe('');
    expect(dsiSelectValue('name', canon)).toBe('');
    expect(dsiSelectValue('channel_key_token', canon)).toBe('channel_key_token');
  });

  it('dsiGateFromMapping accepts inventory date via snapshot stamp', () => {
    expect(
      dsiGateFromMapping(
        {
          b: 'product_identifier',
          d: 'stock_on_hand',
        },
        { fileDistributorSatisfied: true, fileSnapshotSatisfied: true }
      )
    ).toBe(true);
    expect(
      dsiGateFromMapping(
        {
          b: 'product_identifier',
          d: 'stock_on_hand',
        },
        { fileDistributorSatisfied: true, fileSnapshotSatisfied: false }
      )
    ).toBe(false);
  });

  it('dsiDateSatisfiedBySnapshotStamp only when SOH and no date column', () => {
    expect(
      dsiDateSatisfiedBySnapshotStamp(
        { a: 'product_identifier', b: 'stock_on_hand' },
        { fileSnapshotSatisfied: true }
      )
    ).toBe(true);
    expect(
      dsiDateSatisfiedBySnapshotStamp(
        { a: 'snapshot_date', b: 'stock_on_hand' },
        { fileSnapshotSatisfied: true }
      )
    ).toBe(false);
    expect(
      dsiDateSatisfiedBySnapshotStamp(
        { a: 'product_identifier', b: 'quantity_sold' },
        { fileSnapshotSatisfied: true }
      )
    ).toBe(false);
  });

  it('dsiMappingRequiredGroupsFromDraft marks Date OK from stamp for inventory sheets', () => {
    const base = [
      { id: 'distributor', label: 'Distributor', anyOf: ['distributor_token'] },
      { id: 'product', label: 'Product identifier', anyOf: ['product_identifier'] },
      { id: 'date', label: 'Date', anyOf: ['transaction_date', 'snapshot_date'] },
      { id: 'quantity', label: 'Quantity or inventory', anyOf: ['quantity_sold', 'stock_on_hand'] },
    ];
    const groups = dsiMappingRequiredGroupsFromDraft(
      { Model: 'product_identifier', SOH: 'stock_on_hand' },
      {
        baseGroups: base,
        fileDistributorSatisfied: true,
        fileSnapshotSatisfied: true,
      }
    );
    expect(groups.find((g) => g.id === 'distributor')?.externallySatisfied).toBe(true);
    expect(groups.find((g) => g.id === 'date')?.externallySatisfied).toBe(true);

    const sellout = dsiMappingRequiredGroupsFromDraft(
      { Model: 'product_identifier', Qty: 'quantity_sold' },
      {
        baseGroups: base,
        fileDistributorSatisfied: true,
        fileSnapshotSatisfied: true,
      }
    );
    expect(sellout.find((g) => g.id === 'date')?.externallySatisfied).toBe(false);
  });


  it('dsiGateFromNestedMapping requires every sheet to pass', () => {
    const good = {
      a: 'distributor_token',
      b: 'product_identifier',
      c: 'snapshot_date',
      d: 'stock_on_hand',
    };
    expect(dsiGateFromNestedMapping({ Sales: good, SOH: good })).toBe(true);
    expect(dsiGateFromNestedMapping({ Sales: good, SOH: { a: 'distributor_token' } })).toBe(false);
    expect(dsiGateFromNestedMapping({})).toBe(false);
    expect(isNestedDsiFieldMapping({ Sales: good })).toBe(true);
    expect(isNestedDsiFieldMapping({ a: 'distributor_token' })).toBe(false);
  });

  it('groupDsiSheetKeys collapses same layout and detach makes singleton', () => {
    const groups = [
      { signature: 'aaa', mapping_keys: ['a.xlsx::__single__', 'b.xlsx::__single__'], files: ['a.xlsx', 'b.xlsx'] },
      { signature: 'bbb', mapping_keys: ['c.xlsx::__single__'], files: ['c.xlsx'] },
    ];
    const drafts = {
      'a.xlsx::__single__': { Model: 'product_identifier' },
      'b.xlsx::__single__': { Model: 'product_identifier', Qty: 'quantity_sold', Date: 'transaction_date' },
      'c.xlsx::__single__': {},
    };
    const tabs = groupDsiSheetKeys(groups, Object.keys(drafts), [], drafts);
    expect(tabs).toHaveLength(2);
    expect(tabs[0].keys).toHaveLength(2);
    expect(tabs[0].representativeKey).toBe('b.xlsx::__single__');
    expect(tabs[1].keys).toEqual(['c.xlsx::__single__']);

    const detached = groupDsiSheetKeys(groups, Object.keys(drafts), ['a.xlsx::__single__'], drafts);
    expect(detached.some((g) => g.keys.length === 1 && g.keys[0] === 'a.xlsx::__single__')).toBe(true);
    expect(detached.find((g) => g.signature === 'aaa')?.keys).toEqual(['b.xlsx::__single__']);
  });

  it('fanOutDsiLayoutDraft writes the same draft to all member keys', () => {
    const next = fanOutDsiLayoutDraft(
      { 'a.xlsx::__single__': { Old: 'x' } },
      ['a.xlsx::__single__', 'b.xlsx::__single__'],
      { Model: 'product_identifier', Qty: 'quantity_sold' }
    );
    expect(next['a.xlsx::__single__']).toEqual({ Model: 'product_identifier', Qty: 'quantity_sold' });
    expect(next['b.xlsx::__single__']).toEqual({ Model: 'product_identifier', Qty: 'quantity_sold' });
  });


  it('hydrateDsiNestedMapDraft fillMissing preserves dirty sheet edits', () => {
    const canon = new Set(['product_identifier', 'quantity_sold', 'transaction_date']);
    const prev = {
      'a.xlsx::Sheet1': { Model: 'product_identifier', Qty: 'quantity_sold' },
    };
    const next = hydrateDsiNestedMapDraft({
      sheetKeys: ['a.xlsx::Sheet1', 'b.xlsx::Sheet1'],
      serverNested: {
        'a.xlsx::Sheet1': { Model: 'product_identifier' },
        'b.xlsx::Sheet1': { SKU: 'product_identifier', Date: 'transaction_date' },
      },
      prev,
      canonSet: canon,
      mode: 'fillMissing',
    });
    expect(next['a.xlsx::Sheet1']).toEqual(prev['a.xlsx::Sheet1']);
    expect(next['b.xlsx::Sheet1']?.SKU).toBe('product_identifier');
    expect(next['b.xlsx::Sheet1']?.Date).toBe('transaction_date');
  });

  it('hydrateDsiNestedMapDraft replace syncs from server when clean', () => {
    const canon = new Set(['product_identifier']);
    const next = hydrateDsiNestedMapDraft({
      sheetKeys: ['Sheet1'],
      serverNested: { Sheet1: { Model: 'product_identifier', Junk: 'nope' } },
      prev: { Sheet1: { Old: 'product_identifier' } },
      canonSet: canon,
      mode: 'replace',
    });
    expect(next.Sheet1).toEqual({ Model: 'product_identifier' });
  });

  it('stableFieldMappingJson is order-independent', () => {
    const a = stableFieldMappingJson({ b: 'x', a: 'y' });
    const b = stableFieldMappingJson({ a: 'y', b: 'x' });
    expect(a).toBe(b);
  });

  it('parseDistributorSiSummaryFromRows reads summary JSON before applied suffix', () => {
    const rows = [
      {
        row_number: 0,
        code: 'distributor_si_summary',
        message: JSON.stringify({ staging_rows: 3, blocking_rows: 0, warning_rows: 1, aggregated_candidates: 0 }),
      },
    ];
    expect(parseDistributorSiSummaryFromRows(rows)?.blocking_rows).toBe(0);
  });

  it('parseDistributorSiSummaryFromRows uses the latest summary when multiple exist', () => {
    const rows = [
      {
        id: 10,
        row_number: 0,
        code: 'distributor_si_summary',
        message: JSON.stringify({ staging_rows: 178067, blocking_rows: 22522, warning_rows: 1, aggregated_candidates: 799 }),
      },
      {
        id: 99,
        row_number: 0,
        code: 'distributor_si_summary',
        message: JSON.stringify({ staging_rows: 178067, blocking_rows: 194, warning_rows: 10722, aggregated_candidates: 542 }),
      },
    ];
    const s = parseDistributorSiSummaryFromRows(rows);
    expect(s?.blocking_rows).toBe(194);
    expect(s?.aggregated_candidates).toBe(542);
  });

  it('parseDistributorSiSummaryFromRows reads extended DSI counters', () => {
    const rows = [
      {
        row_number: 0,
        code: 'distributor_si_summary',
        message: JSON.stringify({
          staging_rows: 2,
          blocking_rows: 0,
          warning_rows: 2,
          aggregated_candidates: 1,
          sellout_issue_rows: 2,
          rows_inventory_ready_with_sellout_warnings: 2,
        }),
      },
    ];
    const s = parseDistributorSiSummaryFromRows(rows);
    expect(s?.sellout_issue_rows).toBe(2);
    expect(s?.rows_inventory_ready_with_sellout_warnings).toBe(2);
  });

  it('computeDsiContinueGateKey returns null when blockers remain', () => {
    const fm = { a: 'distributor_token' };
    expect(computeDsiContinueGateKey(7, fm, { blocking_rows: 3, human_fixable_blocking_rows: 3 })).toBeNull();
    expect(
      computeDsiContinueGateKey(7, fm, {
        blocking_rows: 0,
        human_fixable_blocking_rows: 0,
        master_merge_excluded_rows: 2,
      })
    ).toBeNull();
    const key = computeDsiContinueGateKey(7, fm, {
      blocking_rows: 0,
      human_fixable_blocking_rows: 0,
      master_merge_excluded_rows: 0,
    });
    expect(key).toBe(`7::${stableFieldMappingJson(fm)}`);
    expect(dsiContinueToApplyAllowed(key, 7, fm, { blocking_rows: 0, human_fixable_blocking_rows: 0 }, { isValidating: false, hasServerGate: true })).toBe(
      true
    );
  });

  it('dsiContinueToApplyAllowed gates on human-fixable blocking rows', () => {
    const fm = { a: 'distributor_token' };
    const key = `7::${stableFieldMappingJson(fm)}`;
    const summary = { staging_rows: 1, blocking_rows: 0, human_fixable_blocking_rows: 0, master_merge_excluded_rows: 21 };
    expect(
      dsiContinueToApplyAllowed(key, 7, fm, summary, { isValidating: false, hasServerGate: true })
    ).toBe(false);
    expect(
      dsiContinueToApplyAllowed(
        key,
        7,
        fm,
        { ...summary, master_merge_excluded_rows: 0 },
        { isValidating: false, hasServerGate: true }
      )
    ).toBe(true);
    expect(
      dsiContinueToApplyAllowed(
        key,
        7,
        fm,
        { ...summary, human_fixable_blocking_rows: 2, blocking_rows: 2 },
        { isValidating: false, hasServerGate: true }
      )
    ).toBe(false);
    expect(dsiContinueToApplyAllowed(key, 7, { ...fm, b: 'x' }, summary, { isValidating: false, hasServerGate: true })).toBe(
      false
    );
    expect(dsiContinueToApplyAllowed(key, 7, fm, summary, { isValidating: true, hasServerGate: true })).toBe(false);
  });

  it('formatDsiBlockerSummaryLine splits master-merge vs steward-map vs blank-product vs auto-excluded', () => {
    expect(
      formatDsiBlockerSummaryLine({
        master_merge_excluded_rows: 21,
        steward_map_blocking_rows: 40,
        data_quality_blocking_rows: 45,
        auto_excluded_rows: 121,
      })
    ).toBe('21 master-merge · 40 steward-map · 45 blank-product · 121 auto-excluded');
    expect(dsiHumanFixableBlockingRows({ human_fixable_blocking_rows: 85, blocking_rows: 85 })).toBe(85);
    expect(
      dsiStewardMapBlockingRows({
        human_fixable_blocking_rows: 85,
        steward_map_blocking_rows: 40,
        data_quality_blocking_rows: 45,
      })
    ).toBe(40);
    expect(dsiDataQualityBlockingRows({ data_quality_blocking_rows: 45 })).toBe(45);
  });
});
