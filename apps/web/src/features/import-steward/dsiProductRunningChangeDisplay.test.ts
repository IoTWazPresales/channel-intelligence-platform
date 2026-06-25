import { describe, expect, it } from 'vitest';

import {
  dsiIgnoreReasonCodeLabel,
  formatDsiProductMatchFifoWarning,
  formatDsiProductRunningChangeSummary,
  isDsiTokenLevelResolveProductBlocked,
} from './dsiProductRunningChangeDisplay';

describe('dsiProductRunningChangeDisplay', () => {
  it('formats running-change summary from quality block', () => {
    const s = formatDsiProductRunningChangeSummary({
      product_resolution_quality: {
        total_rows: 1470,
        resolved_receipt_temporal: 543,
        indeterminate_rows: 927,
      },
      product_running_change_received_both: true,
    });
    expect(s).toBe('543 of 1470 resolved by shipment receipt/temporal; 927 indeterminate (received-both)');
  });

  it('prefers product_match_summary when already enriched', () => {
    const s = formatDsiProductRunningChangeSummary({
      product_match_summary: '12 of 20 resolved by shipment receipt/temporal; 8 indeterminate',
    });
    expect(s).toBe('12 of 20 resolved by shipment receipt/temporal; 8 indeterminate');
  });

  it('blocks token-level resolve when receipt/temporal context present', () => {
    expect(
      isDsiTokenLevelResolveProductBlocked({
        product_ambiguous_eligible: { product_ids: [1, 2] },
        receipt_disambiguation: { status: 'ambiguous_overlap' },
      })
    ).toBe(true);
    expect(
      isDsiTokenLevelResolveProductBlocked({
        product_ambiguous_eligible: { product_ids: [1] },
        receipt_disambiguation: { status: 'resolved_single' },
      })
    ).toBe(false);
  });

  it('labels ignore reason codes', () => {
    expect(dsiIgnoreReasonCodeLabel('ignore_sku_indeterminate')).toContain('indeterminate');
    expect(dsiIgnoreReasonCodeLabel('ignore_no_catalogue')).toContain('no catalogue');
    expect(dsiIgnoreReasonCodeLabel('ignore_no_receipt_evidence')).toContain('receipt');
  });

  it('formats fifo warning for match cell', () => {
    expect(
      formatDsiProductMatchFifoWarning({
        fifo_candidate: true,
        temporal_supersession: { fifo_candidate: false },
      })
    ).toContain('FIFO candidate');
  });
});
