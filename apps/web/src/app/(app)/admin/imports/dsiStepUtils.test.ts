import { describe, expect, it } from 'vitest';

import { dsiGateFromMapping, dsiSelectValue, dsiTargetLabel } from './dsiStepUtils';

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
});
