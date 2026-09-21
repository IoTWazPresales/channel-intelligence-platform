import { describe, expect, it } from 'vitest';

import { mapSettlementDeskView, type SettlementDeskApi, type SettlementDeskCase } from './mapSettlementDeskView';

const detail: SettlementDeskCase = {
  id: 311,
  case_code: 'C26760971',
  customer_code: 'CUST-000012',
  customer_name: 'Takealot',
  promotion_type: 'Pinnacle',
  window_start: '2026-07-30',
  window_end: '2026-08-31',
  status: 'settled',
  currency_code: 'ZAR',
  decided_by: null,
  allowed_next: [],
};

describe('mapSettlementDeskView', () => {
  it('keeps an empty customer tape empty and flags settled-without-claims', () => {
    const settlement: SettlementDeskApi = {
      case_id: 311,
      status: 'settled',
      window_start: '2026-07-30',
      window_end: '2026-08-31',
      claim_row_count: 0,
      can_settle: false,
      lines: [
        {
          line_id: 1,
          product_id: 9,
          product_sku: '90NB0ZR2-M06MU0',
          product_name: 'NB',
          distributor_name: 'Pinnacle',
          estimate_qty: 10,
          result_qty: null,
          cip_qty: 8,
          customer_qty: null,
          corroboration: 'pending',
          corroboration_reason: 'Awaiting customer',
          include_in_credit: false,
          support_unit: 100,
        },
      ],
      desk: {
        cip_amount: 800,
        customer_amount: null,
        agreed_amount: null,
        paid_amount: null,
        paid_in_schema: false,
        hq_credit_amount: null,
        hq_credit_line_count: 0,
        matched_count: 0,
        open_count: 1,
        cip_qty_grain: 'product',
        agreed_actor: null,
      },
    };
    const view = mapSettlementDeskView(detail, settlement);
    expect(view.customerName).toBe('Takealot');
    // Name-primary, code suppressed (Warren 2026-09-21): the mapper still carries the field,
    // but customerSecondaryCode withholds it so no identity position can render it.
    expect(view.customerCode).toBeNull();
    expect(view.settledWithoutClaims).toBe(true);
    expect(view.lines[0].customerQty).toBeNull();
    expect(view.customerAmount).toBeNull();
  });
});
