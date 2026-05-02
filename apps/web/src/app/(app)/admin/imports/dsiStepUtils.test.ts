import { describe, expect, it } from 'vitest';

import {
  dsiContinueToApplyAllowed,
  dsiGateFromMapping,
  dsiSelectValue,
  dsiTargetLabel,
  parseDistributorSiSummaryFromRows,
  stableFieldMappingJson,
} from './dsiStepUtils';

describe('dsiStepUtils', () => {
  it('uses friendly labels for key DSI targets', () => {
    expect(dsiTargetLabel('product_identifier')).toMatch(/SKU/i);
    expect(dsiTargetLabel('product_identifier')).toMatch(/part/i);
    expect(dsiTargetLabel('distributor_token')).toBe('Distributor');
    expect(dsiTargetLabel('channel_key_token')).toMatch(/Channel/i);
  });

  it('dsiSelectValue never returns unknown canonical targets', () => {
    const canon = new Set(['distributor_token', 'channel_key_token']);
    expect(dsiSelectValue('channel_code', canon)).toBe('');
    expect(dsiSelectValue('name', canon)).toBe('');
    expect(dsiSelectValue('channel_key_token', canon)).toBe('channel_key_token');
  });

  it('dsiGateFromMapping enforces required DSI mappings', () => {
    expect(dsiGateFromMapping({})).toBe(false);
    expect(
      dsiGateFromMapping({
        a: 'distributor_token',
        b: 'product_identifier',
        c: 'transaction_date',
        d: 'quantity_sold',
      })
    ).toBe(true);
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

  it('dsiContinueToApplyAllowed gates on job, mapping key, and blocking rows', () => {
    const fm = { a: 'distributor_token' };
    const key = `7::${stableFieldMappingJson(fm)}`;
    const summary = { staging_rows: 1, blocking_rows: 0 };
    expect(
      dsiContinueToApplyAllowed(key, 7, fm, summary, { isValidating: false, hasServerGate: true })
    ).toBe(true);
    expect(
      dsiContinueToApplyAllowed(key, 7, fm, { ...summary, blocking_rows: 2 }, { isValidating: false, hasServerGate: true })
    ).toBe(false);
    expect(dsiContinueToApplyAllowed(key, 7, { ...fm, b: 'x' }, summary, { isValidating: false, hasServerGate: true })).toBe(
      false
    );
    expect(dsiContinueToApplyAllowed(key, 7, fm, summary, { isValidating: true, hasServerGate: true })).toBe(false);
  });
});
