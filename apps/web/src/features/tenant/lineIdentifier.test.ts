import { describe, expect, it } from 'vitest';

import { lineIdentifierHeader, lineIdentifierValue } from './lineIdentifier';

describe('lineIdentifier', () => {
  it('defaults the header to SKU', () => {
    expect(lineIdentifierHeader('sku')).toBe('SKU');
    expect(lineIdentifierHeader('sales_model')).toBe('Sales model');
  });

  it('does not drop the other identifier — it is the fallback only', () => {
    expect(lineIdentifierValue('sku', '90NB', 'Vivobook')).toBe('90NB');
    expect(lineIdentifierValue('sales_model', '90NB', 'Vivobook')).toBe('Vivobook');
    expect(lineIdentifierValue('sales_model', '90NB', null)).toBe('90NB');
    expect(lineIdentifierValue('sku', null, 'Vivobook')).toBe('Vivobook');
  });
});
