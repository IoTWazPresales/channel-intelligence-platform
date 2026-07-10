import { describe, expect, it } from 'vitest';

import type { DsiCandidateRow } from './dsi-mapping-steward-panel';
import {
  buildDsiProductCandidateExportRows,
  dsiProductCandidateExportToCsv,
} from './dsiProductCandidateExport';

function productRow(partial: Partial<DsiCandidateRow>): DsiCandidateRow {
  return {
    id: 1,
    entity_type: 'product_identifier',
    normalized_key: 'sku-a',
    status: 'needs_review',
    row_count: 10,
    total_units: 100,
    total_reported_value: 5000,
    sample_raw_values: ['SKU-A'],
    context: {
      product_resolution_quality: {
        resolved_receipt_temporal: 4,
        indeterminate_rows: 6,
      },
      unresolved_distributor_ids: [1, 2],
      dominant_evidence_month: '2025-03',
      steward_ignore_reason_code: 'ignore_sku_indeterminate',
    },
    ...partial,
  } as DsiCandidateRow;
}

describe('dsiProductCandidateExport', () => {
  it('builds quality columns from candidate context', () => {
    const rows = buildDsiProductCandidateExportRows([productRow({})]);
    expect(rows).toHaveLength(1);
    expect(rows[0]?.token).toBe('SKU-A');
    expect(rows[0]?.resolved_receipt_temporal).toBe(4);
    expect(rows[0]?.indeterminate).toBe(6);
    expect(rows[0]?.reason_code).toBe('ignore_sku_indeterminate');
    expect(rows[0]?.distributors).toBe('1; 2');
    expect(rows[0]?.dominant_month).toBe('2025-03');
  });

  it('serializes csv with header row', () => {
    const csv = dsiProductCandidateExportToCsv(buildDsiProductCandidateExportRows([productRow({})]));
    expect(csv.split('\r\n')[0]).toContain('token,rows,units,value');
    expect(csv).toContain('SKU-A');
  });

  it('ignores non-product candidates', () => {
    const rows = buildDsiProductCandidateExportRows([
      productRow({ entity_type: 'customer_dealer_token' as 'product_identifier' }),
    ]);
    expect(rows).toHaveLength(0);
  });
});
