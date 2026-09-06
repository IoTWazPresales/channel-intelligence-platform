import { describe, expect, it } from 'vitest';

import { dataLensFromPath } from './DataChrome';

describe('dataLensFromPath', () => {
  it('maps production Data & Stewardship routes onto the lab lenses', () => {
    expect(dataLensFromPath('/admin/imports')).toBe('imports');
    expect(dataLensFromPath('/admin/imports?template=customer_sell_through')).toBe('imports');
    expect(dataLensFromPath('/admin/mappings')).toBe('steward');
    expect(dataLensFromPath('/admin/masters')).toBe('masters');
    expect(dataLensFromPath('/admin/products')).toBe('masters');
    expect(dataLensFromPath('/admin/customers')).toBe('masters');
    expect(dataLensFromPath('/admin/distributors')).toBe('masters');
    expect(dataLensFromPath('/admin/steward-audit')).toBe('audit');
  });
});
