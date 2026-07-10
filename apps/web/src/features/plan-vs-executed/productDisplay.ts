export type ProductGroupBy = 'description' | 'sku' | 'sales_model';

export type ProductCatalogFields = {
  product_name?: string | null;
  product_description?: string | null;
  product_marketing_name?: string | null;
  product_sales_model?: string | null;
  product_sku?: string | null;
};

export type ProductDisplay = {
  primary: string;
  secondary: string | null;
  labelFallback: boolean;
};

/** Human-readable product label — description → sales_model → SKU; never bare internal id. */
export function resolveProductDisplay(
  row: ProductCatalogFields,
  groupBy: ProductGroupBy = 'description',
): ProductDisplay {
  const description = (
    row.product_marketing_name ||
    row.product_description ||
    row.product_name ||
    ''
  ).trim();
  const salesModel = (row.product_sales_model || '').trim();
  const sku = (row.product_sku || '').trim();

  let labelFallback = !description;

  if (groupBy === 'sku') {
    const primary = sku || salesModel || description || '—';
    const secondaryParts = [description, salesModel].filter((p) => p && p !== primary);
    return {
      primary,
      secondary: secondaryParts.length ? secondaryParts.join(' · ') : null,
      labelFallback: !description && !salesModel,
    };
  }

  if (groupBy === 'sales_model') {
    const primary = salesModel || description || sku || 'Unspecified sales model';
    const secondaryParts = [description, sku].filter((p) => p && p !== primary);
    return {
      primary,
      secondary: secondaryParts.length ? secondaryParts.join(' · ') : null,
      labelFallback: !description,
    };
  }

  const primary = description || salesModel || sku || '—';
  if (!description) labelFallback = true;
  const secondaryParts = [salesModel, sku].filter(Boolean);
  return {
    primary,
    secondary: secondaryParts.length ? secondaryParts.join(' · ') : null,
    labelFallback,
  };
}

export function buildPlanVsExecutedHref(opts: {
  periodFrom: string;
  periodTo?: string;
  productLine?: string | null;
}): string {
  const p = new URLSearchParams();
  p.set('period_from', opts.periodFrom);
  p.set('period_to', opts.periodTo ?? opts.periodFrom);
  if (opts.productLine) p.set('product_line', opts.productLine);
  return `/plan-vs-executed?${p.toString()}`;
}
