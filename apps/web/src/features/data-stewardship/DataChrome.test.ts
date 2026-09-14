import { describe, expect, it } from 'vitest';

import { dataAlsoHereItems } from './dataAlsoHere';
import { dataLensFromPath } from './DataChrome';

const TAB_HREFS = [
  '/admin/imports',
  '/admin/mappings',
  '/admin/masters',
  '/admin/steward-audit',
];

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

describe('dataAlsoHereItems', () => {
  it('lists Products, Customers, duplicates, CST and gaps without adding tabs', () => {
    const labels = dataAlsoHereItems('admin', TAB_HREFS).map((l) => l.label);
    expect(labels).toContain('Products');
    expect(labels).toContain('Customers');
    expect(labels).toContain('Customer duplicates');
    expect(labels).toContain('Customer sell-through files');
    expect(labels).toContain('Product catalogue gaps');
    expect(labels).toContain('CST steward');
    expect(labels).not.toContain('Import Center');
    expect(labels).not.toContain('Steward queue');
    expect(labels).not.toContain('Master data');
    expect(labels).not.toContain('Steward audit');
  });
});
