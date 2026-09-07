import { describe, expect, it } from 'vitest';

import { supplyLensFromPath } from './supplyPaths';

describe('supplyLensFromPath', () => {
  it('maps production Supply & Inbound routes onto lab leaves', () => {
    expect(supplyLensFromPath('/supply')).toBe('hub');
    expect(supplyLensFromPath('/supply/shipments')).toBe('shipments');
    expect(supplyLensFromPath('/admin/shipment-evidence')).toBe('receipts');
    expect(supplyLensFromPath('/admin/po-management')).toBe('po');
  });
});
