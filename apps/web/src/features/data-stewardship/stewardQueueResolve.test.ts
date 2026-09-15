import { describe, expect, it } from 'vitest';

import {
  cstTabForEntityType,
  dsiTabForEntityType,
  parsePositiveInt,
  shipmentTabForEntityType,
  stewardResolveEngine,
} from './stewardQueueResolve';

describe('stewardQueueResolve', () => {
  it('maps known entity types onto the existing engines and tabs', () => {
    expect(stewardResolveEngine('customer_dealer_token')).toBe('dsi');
    expect(dsiTabForEntityType('customer_dealer_token')).toBe('customer');
    expect(dsiTabForEntityType('distributor_token')).toBe('distributor');
    expect(dsiTabForEntityType('product_identifier')).toBe('product');
    expect(stewardResolveEngine('cst_location_token')).toBe('cst');
    expect(cstTabForEntityType('cst_location_token')).toBe('location');
    expect(stewardResolveEngine('shipment_customer_token')).toBe('shipment');
    expect(shipmentTabForEntityType('shipment_distributor')).toBe('distributor');
  });

  it('does not invent an engine for unknown types', () => {
    expect(stewardResolveEngine('brand_new_token')).toBeNull();
    expect(dsiTabForEntityType('cst_product_token')).toBeNull();
  });

  it('parses job and candidate ids', () => {
    expect(parsePositiveInt('900')).toBe(900);
    expect(parsePositiveInt('0')).toBeNull();
    expect(parsePositiveInt('job')).toBeNull();
  });
});
