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
}

export function buildShippingCommercialSummaryUrl(p: ShippingFilterParams): string {
  const params = new URLSearchParams();
  appendShippingFilterParams(params, p);
  const qs = params.toString();
  return qs ? `/api/v1/shipping/commercial-summary?${qs}` : '/api/v1/shipping/commercial-summary';
}

export function buildShippingEtaShiftsUrl(p: ShippingFilterParams, sampleLimit: number): string {
  const params = new URLSearchParams();
  params.set('sample_limit', String(sampleLimit));
  appendShippingFilterParams(params, p);
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
