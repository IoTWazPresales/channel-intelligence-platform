import { describe, expect, it } from 'vitest';

import {
  buildShippingCommercialSummaryUrl,
  buildShippingLinesUrl,
} from './buildShippingLinesUrl';

describe('buildShippingLinesUrl', () => {
  it('includes skip and limit', () => {
    const url = buildShippingLinesUrl({
      skip: 100,
      limit: 50,
      lineState: '',
      cargoStatus: '',
      distributorId: null,
      customerId: null,
      purchaseOrderId: null,
      search: '',
      dateField: 'eta_date',
      dateFrom: '',
      dateTo: '',
      productFamily: '',
      productModel: '',
      currencyCode: '',
      operatingUnit: '',
      podDateFilter: '',
      includeRawRow: false,
    });
    expect(url).toContain('skip=100');
    expect(url).toContain('limit=50');
  });

  it('serializes filters', () => {
    const url = buildShippingLinesUrl({
      skip: 0,
      limit: 25,
      lineState: 'open_order',
      cargoStatus: 'scheduled',
      distributorId: 3,
      customerId: null,
      purchaseOrderId: 77,
      search: 'acme',
      dateField: 'promise_date',
      dateFrom: '2026-06-01',
      dateTo: '2026-06-07',
      productFamily: '',
      productModel: '',
      currencyCode: 'USD',
      operatingUnit: '',
      podDateFilter: 'true',
      includeRawRow: true,
    });
    expect(url).toContain('line_state=open_order');
    expect(url).toContain('status=scheduled');
    expect(url).toContain('distributor_id=3');
    expect(url).toContain('purchase_order_id=77');
    expect(url).toContain('search=acme');
    expect(url).toContain('pod_date_is_null=true');
    expect(url).toContain('include_raw_row=true');
  });

  it('builds commercial-summary URL without pagination', () => {
    const url = buildShippingCommercialSummaryUrl({
      lineState: '',
      cargoStatus: 'received',
      distributorId: null,
      customerId: null,
      purchaseOrderId: null,
      search: '',
      dateField: 'pod_date',
      dateFrom: '',
      dateTo: '',
      productFamily: '',
      productModel: '',
      currencyCode: '',
      operatingUnit: '',
      podDateFilter: 'false',
    });
    expect(url).toContain('/commercial-summary');
    expect(url).toContain('status=received');
    expect(url).toContain('pod_date_is_null=false');
    expect(url).not.toContain('skip=');
    expect(url).not.toContain('limit=');
  });
});
