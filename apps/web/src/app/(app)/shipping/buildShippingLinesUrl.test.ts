import { describe, expect, it } from 'vitest';

import {
  buildShippingCommercialSummaryUrl,
  buildShippingEtaShiftsUrl,
  buildShippingLinesUrl,
} from './buildShippingLinesUrl';

const emptyFilters = {
  lineState: '',
  cargoStatus: '',
  distributorId: null as number | null,
  customerId: null as number | null,
  purchaseOrderId: null as number | null,
  search: '',
  dateField: 'eta_date',
  dateFrom: '',
  dateTo: '',
  productFamily: '',
  productModel: '',
  currencyCode: '',
  operatingUnit: '',
  podDateFilter: '' as const,
  planQuarter: '',
  planBusinessUnit: '',
  lineupAttribution: '' as const,
  lifecycleBucket: '' as const,
  slipDirection: '' as const,
  cohort: '' as const,
};

describe('buildShippingLinesUrl', () => {
  it('includes skip and limit', () => {
    const url = buildShippingLinesUrl({
      ...emptyFilters,
      skip: 100,
      limit: 50,
      includeRawRow: false,
    });
    expect(url).toContain('skip=100');
    expect(url).toContain('limit=50');
  });

  it('serializes filters including cohort and lineup', () => {
    const url = buildShippingLinesUrl({
      ...emptyFilters,
      skip: 0,
      limit: 25,
      lineState: 'open_order',
      cargoStatus: 'scheduled',
      distributorId: 3,
      purchaseOrderId: 77,
      search: 'acme',
      dateField: 'promise_date',
      dateFrom: '2026-06-01',
      dateTo: '2026-06-07',
      currencyCode: 'USD',
      podDateFilter: 'true',
      planQuarter: '2026 Q2',
      planBusinessUnit: 'NB',
      lifecycleBucket: 'shipped',
      slipDirection: 'slipped_out',
      cohort: 'current_incoming',
      includeRawRow: true,
    });
    expect(url).toContain('line_state=open_order');
    expect(url).toContain('plan_quarter=2026+Q2');
    expect(url).toContain('lifecycle_bucket=shipped');
    expect(url).toContain('status=scheduled');
    expect(url).toContain('distributor_id=3');
    expect(url).toContain('purchase_order_id=77');
    expect(url).toContain('search=acme');
    expect(url).toContain('pod_date_is_null=true');
    expect(url).toContain('cohort=current_incoming');
    expect(url).toContain('include_raw_row=true');
  });

  it('builds commercial-summary URL without pagination and keeps filter parity', () => {
    const url = buildShippingCommercialSummaryUrl({
      ...emptyFilters,
      cargoStatus: 'received',
      dateField: 'pod_date',
      podDateFilter: 'false',
      planQuarter: '2026Q3',
      cohort: 'overdue',
    });
    expect(url).toContain('/commercial-summary');
    expect(url).toContain('status=received');
    expect(url).toContain('pod_date_is_null=false');
    expect(url).toContain('plan_quarter=2026Q3');
    expect(url).toContain('cohort=overdue');
    expect(url).not.toContain('skip=');
    expect(url).not.toContain('limit=');
  });

  it('leaves a clicked vessel and the needs-a-look cohort out of the tiles and the ETA shifts, so only the grid refreshes', () => {
    const picked = { ...emptyFilters, vessel: 'i:2026-09-19|2026-11-05|ZAJNB|asia_durban', cohort: 'needs_look' as const };
    expect(buildShippingCommercialSummaryUrl(picked)).toBe(buildShippingCommercialSummaryUrl(emptyFilters));
    expect(buildShippingEtaShiftsUrl(picked, 5)).toBe(buildShippingEtaShiftsUrl(emptyFilters, 5));
    expect(buildShippingLinesUrl({ ...picked, skip: 0, limit: 50, includeRawRow: false })).toContain('vessel=');
    expect(buildShippingLinesUrl({ ...picked, skip: 0, limit: 50, includeRawRow: false })).toContain('cohort=needs_look');
  });
});
