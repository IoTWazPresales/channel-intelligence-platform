/** Customer rollup for the Execution vs plan lab strip. Pure; numbers come from the plan-vs-executed read model. */

export type ExecutionLine = {
  customer_label?: string | null;
  customer_id?: number | null;
  planned_units?: number | null;
  shipped_units?: number | null;
};

export type CustomerPlanShipped = { customer: string; plan: number; shipped: number };

export function rollCustomers(rows: ExecutionLine[]): CustomerPlanShipped[] {
  const map = new Map<string, CustomerPlanShipped>();
  for (const r of rows) {
    const key =
      (r.customer_label || '').trim() ||
      (r.customer_id != null ? `Customer ${r.customer_id}` : 'Unnamed');
    const cur = map.get(key) ?? { customer: key, plan: 0, shipped: 0 };
    cur.plan += Number(r.planned_units) || 0;
    cur.shipped += Number(r.shipped_units) || 0;
    map.set(key, cur);
  }
  return [...map.values()].sort((a, b) => b.plan - a.plan);
}

export function customersUnderPlanShare(rows: CustomerPlanShipped[], threshold = 0.7): number {
  return rows.filter((r) => r.plan > 0 && r.shipped / r.plan < threshold).length;
}
