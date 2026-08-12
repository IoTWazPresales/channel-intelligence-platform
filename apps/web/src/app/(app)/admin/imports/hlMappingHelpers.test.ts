import { describe, expect, it } from 'vitest';

import { hlFieldMapToHeaderDraft, hlHeaderDraftToOverride } from './hlMappingHelpers';

describe('hlFieldMapToHeaderDraft', () => {
  it('inverts canonical → column to column → canonical', () => {
    expect(
      hlFieldMapToHeaderDraft({
        customer_token: 'Customer',
        sku_raw: 'SKU',
      })
    ).toEqual({ Customer: 'customer_token', SKU: 'sku_raw' });
  });
});

describe('hlHeaderDraftToOverride', () => {
  it('omits unchanged detected mappings', () => {
    const detected = { customer_token: 'Customer', sku_raw: 'SKU' };
    const draft = { Customer: 'customer_token', SKU: 'sku_raw' };
    expect(hlHeaderDraftToOverride('Sheet1', draft, detected)).toEqual({});
  });

  it('emits only changed canonical → column pairs', () => {
    const detected = { customer_token: 'Customer', sku_raw: 'SKU' };
    const draft = { Buyer: 'customer_token', SKU: 'sku_raw' };
    expect(hlHeaderDraftToOverride('Sheet1', draft, detected)).toEqual({
      Sheet1: { customer_token: 'Buyer' },
    });
  });
});
