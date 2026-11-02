export type ShippingFilterParams = {
  lineState: string;
  cargoStatus: string;
  distributorId: number | null;
  customerId: number | null;
  purchaseOrderId: number | null;
  search: string;
  dateField: string;
  dateFrom: string;
  dateTo: string;
  productFamily: string;
  productModel: string;
  currencyCode: string;
  operatingUnit: string;
  podDateFilter: '' | 'true' | 'false';
  planQuarter: string;
  planBusinessUnit: string;
  lineupAttribution: '' | 'unattributed';
  lifecycleBucket: '' | 'shipped' | 'pipeline' | 'landed';
  slipDirection: '' | 'slipped_in' | 'slipped_out';
  /** Smart-preset / card-click cohort — same predicates as commercial KPI contract. */
  cohort: '' | 'current_incoming' | 'overdue' | 'arriving_week' | 'landed_week' | 'needs_look';
  /** One vessel's lines (the key from the On the water payload). The map itself ignores it. */
  vessel?: string;
};

export type ShippingLinesQueryParams = ShippingFilterParams & {
  skip: number;
  limit: number;
  includeRawRow: boolean;
};

/** Append filter query params shared by ``/lines``, ``/commercial-summary``, and ``/eta-shifts``. */
export function appendShippingFilterParams(params: URLSearchParams, p: ShippingFilterParams): void {
  if (p.lineState) params.set('line_state', p.lineState);
  if (p.cargoStatus) params.set('status', p.cargoStatus);
  if (p.distributorId != null) params.set('distributor_id', String(p.distributorId));
  if (p.customerId != null) params.set('customer_id', String(p.customerId));
  if (p.purchaseOrderId != null) params.set('purchase_order_id', String(p.purchaseOrderId));
  if (p.search.trim()) params.set('search', p.search.trim());
  if (p.dateField) params.set('date_field', p.dateField);
  if (p.dateFrom.trim()) params.set('date_from', p.dateFrom.trim());
  if (p.dateTo.trim()) params.set('date_to', p.dateTo.trim());
  if (p.productFamily.trim()) params.set('product_family', p.productFamily.trim());
  if (p.productModel.trim()) params.set('product_model', p.productModel.trim());
  if (p.currencyCode.trim()) params.set('currency_code', p.currencyCode.trim());
  if (p.operatingUnit.trim()) params.set('operating_unit', p.operatingUnit.trim());
  if (p.podDateFilter === 'true') params.set('pod_date_is_null', 'true');
  if (p.podDateFilter === 'false') params.set('pod_date_is_null', 'false');
  if (p.planQuarter.trim()) params.set('plan_quarter', p.planQuarter.trim());
  if (p.planBusinessUnit.trim()) params.set('plan_business_unit', p.planBusinessUnit.trim());
  if (p.lineupAttribution === 'unattributed') params.set('lineup_attribution', 'unattributed');
  if (p.lifecycleBucket) params.set('lifecycle_bucket', p.lifecycleBucket);
  if (p.slipDirection) params.set('slip_direction', p.slipDirection);
  if (p.cohort) params.set('cohort', p.cohort);
  if (p.vessel) params.set('vessel', p.vessel);
}

/**
 * On the water map and tiles: only who the page is about (distributor, customer, purchase order, product, currency, plan).
 * Everything that picks lines out of that for the grid (line state, status, dates, search, POD, lifecycle, slip, a smart preset or
 * card cohort, a clicked vessel) is left out, so clicking a vessel, a list row or "Open the lines" changes the grid and the map
 * keeps its query and does not refetch.
 */
export function buildOnTheWaterUrl(p: ShippingFilterParams): string {
  const params = new URLSearchParams();
  appendShippingFilterParams(params, {
    ...p,
    lineState: '',
    cargoStatus: '',
    search: '',
    dateField: '',
    dateFrom: '',
    dateTo: '',
    podDateFilter: '',
    lifecycleBucket: '',
    slipDirection: '',
    cohort: '',
    vessel: '',
  });
  const qs = params.toString();
  return qs ? `/api/v1/shipping/on-the-water?${qs}` : '/api/v1/shipping/on-the-water';
}

export function buildShippingLineupQuarterSummaryUrl(
  planQuarter: string,
  customerId: number | null,
  planBusinessUnit: string,
): string {
  const params = new URLSearchParams();
  params.set('plan_quarter', planQuarter);
  if (customerId != null) params.set('customer_id', String(customerId));
  if (planBusinessUnit.trim()) params.set('plan_business_unit', planBusinessUnit.trim());
  return `/api/v1/shipping/lineup-quarter-summary?${params.toString()}`;
}

/** A clicked vessel and the needs-a-look cohort pick lines for the grid only: the tiles keep their own query and do not refetch. */
function withoutGridSelection(p: ShippingFilterParams): ShippingFilterParams {
  return { ...p, vessel: '', cohort: p.cohort === 'needs_look' ? '' : p.cohort };
}

export function buildShippingCommercialSummaryUrl(p: ShippingFilterParams): string {
  const params = new URLSearchParams();
  appendShippingFilterParams(params, withoutGridSelection(p));
  const qs = params.toString();
  return qs ? `/api/v1/shipping/commercial-summary?${qs}` : '/api/v1/shipping/commercial-summary';
}

export function buildShippingEtaShiftsUrl(p: ShippingFilterParams, sampleLimit: number): string {
  const params = new URLSearchParams();
  params.set('sample_limit', String(sampleLimit));
  appendShippingFilterParams(params, withoutGridSelection(p));
  return `/api/v1/shipping/eta-shifts?${params.toString()}`;
}

export function buildShippingLinesUrl(p: ShippingLinesQueryParams): string {
  const params = new URLSearchParams();
  params.set('skip', String(p.skip));
  params.set('limit', String(p.limit));
  appendShippingFilterParams(params, p);
  if (p.includeRawRow) params.set('include_raw_row', 'true');
  return `/api/v1/shipping/lines?${params.toString()}`;
}
