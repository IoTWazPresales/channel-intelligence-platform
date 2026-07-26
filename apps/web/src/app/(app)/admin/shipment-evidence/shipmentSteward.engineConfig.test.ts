import { describe, expect, it } from 'vitest';

import { normalizeShipmentBulkApplyResult } from './shipmentBulkStewardPoll';
import { SHIPMENT_BULK_ENGINE_CONFIG, SHIPMENT_ENGINE_CONFIG } from './shipmentSteward.engineConfig';

describe('shipmentSteward.engineConfig bulk binding', () => {
  it('exposes shipment bulk preview/apply paths', () => {
    expect(SHIPMENT_ENGINE_CONFIG.bulkPreviewPath(42)).toBe(
      '/api/v1/shipment-evidence/import-jobs/42/shipment-steward-bulk-preview'
    );
    expect(SHIPMENT_ENGINE_CONFIG.bulkApplyPath(42)).toBe(
      '/api/v1/shipment-evidence/import-jobs/42/shipment-steward-bulk-apply'
    );
    expect(SHIPMENT_ENGINE_CONFIG.bulkIgnoreAsyncPath(42)).toContain('shipment-steward-bulk-ignore');
    expect(SHIPMENT_ENGINE_CONFIG.bulkProvisionalCustomersAsyncPath(42)).toContain(
      'shipment-steward-bulk-provisional-customers'
    );
  });

  it('uses shipment_bulk background kinds', () => {
    expect(SHIPMENT_BULK_ENGINE_CONFIG.bulkIgnoreBackgroundKind).toBe('shipment_bulk');
    expect(SHIPMENT_BULK_ENGINE_CONFIG.bulkProvisionalBackgroundKind).toBe('shipment_bulk');
  });

  it('exposes effective plan path for toolbar refresh', () => {
    expect(SHIPMENT_ENGINE_CONFIG.effectivePlanPath?.(7)).toBe(
      '/api/v1/shipment-evidence/import-jobs/7/resolution-plan/effective'
    );
  });
});

describe('normalizeShipmentBulkApplyResult', () => {
  it('maps ignore async runner payload to steward bulk apply envelope', () => {
    const out = normalizeShipmentBulkApplyResult(9, {
      import_job_id: 9,
      action: 'ignore',
      applied: 2,
      failed: 1,
      results: [
        { candidate_id: 1, ok: true },
        { candidate_id: 2, ok: true },
        { candidate_id: 3, ok: false },
      ],
    });
    expect(out).toEqual({
      import_job_id: 9,
      action: 'ignore',
      applied: 2,
      failed: 1,
      results: [
        { candidate_id: 1, ok: true },
        { candidate_id: 2, ok: true },
        { candidate_id: 3, ok: false },
      ],
    });
  });

  it('derives applied/failed counts when omitted', () => {
    const out = normalizeShipmentBulkApplyResult(1, {
      action: 'create_provisional_customer',
      results: [{ candidate_id: 5, ok: true }, { candidate_id: 6, ok: false }],
    });
    expect(out.applied).toBe(1);
    expect(out.failed).toBe(1);
  });
});
