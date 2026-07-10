/** Deep-link into inbound shipments with lineup plan-quarter pre-filters (from PvE drill). */
export function buildInboundShipmentsHref(opts: {
  planQuarter: string;
  customerId?: number | null;
  planBusinessUnit?: string | null;
}): string {
  const p = new URLSearchParams();
  p.set('plan_quarter', opts.planQuarter);
  if (opts.customerId != null) p.set('customer_id', String(opts.customerId));
  if (opts.planBusinessUnit) p.set('plan_business_unit', opts.planBusinessUnit);
  const qs = p.toString();
  return `/shipping?${qs}`;
}
