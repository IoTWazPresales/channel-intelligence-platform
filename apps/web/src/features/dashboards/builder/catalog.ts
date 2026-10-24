/**
 * Catalog helpers shared by the card, the filter bar and the editor: measure and model lookups,
 * breakdown labels, units, additivity. All read the v2 catalog; nothing is guessed from a value.
 */

import { metricPresentation } from '@/features/reports/reportPresentation';
import type { MeasureUnit } from '@/features/workbench-ui/charts';

import type { CatalogV2, DefinitionV2, V2Measure, V2Model, V2Unit } from './types';

export function measureOf(catalog: CatalogV2 | null | undefined, id: string): V2Measure | undefined {
  return catalog?.measures.find((m) => m.id === id);
}

export function modelOf(catalog: CatalogV2 | null | undefined, id: string | null | undefined): V2Model | undefined {
  if (!id) return undefined;
  return catalog?.models.find((m) => m.id === id);
}

export function definitionMeasures(catalog: CatalogV2 | null | undefined, def: DefinitionV2): V2Measure[] {
  return def.query.measures.map((id) => measureOf(catalog, id)).filter((m): m is V2Measure => Boolean(m));
}

/** Model / governed kind of a definition: the stored kind, else from its first measure. */
export function definitionKind(catalog: CatalogV2 | null | undefined, def: DefinitionV2): 'model' | 'governed' {
  if (def.kind) return def.kind;
  const m = measureOf(catalog, def.query.measures[0] ?? '');
  return m?.kind === 'governed' ? 'governed' : 'model';
}

const FALLBACK_LABEL: Record<string, string> = {
  period: 'Period',
  customer: 'Customer',
  distributor: 'Distributor',
  product: 'Product',
  bu: 'Business unit (product line)',
  channel: 'Channel (current)',
  region: 'Region (current)',
  site_label: 'Store / site',
  promo_type: 'Promotion type',
  status: 'Case status',
  workflow_status: 'Case approval status',
};

export function breakdownLabel(catalog: CatalogV2 | null | undefined, id: string): string {
  return catalog?.breakdowns.find((b) => b.id === id)?.label ?? FALLBACK_LABEL[id] ?? id.replace(/_/g, ' ');
}

/** "Store / site" -> "store / site"; acronyms ("CPOR ...") keep their case. */
export function lowerFirst(s: string): string {
  if (s.length > 1 && s[0] === s[0].toUpperCase() && s[1] === s[1].toUpperCase() && /[A-Z]/.test(s[1])) return s;
  return s.charAt(0).toLowerCase() + s.slice(1);
}

export function breakdownKind(catalog: CatalogV2 | null | undefined, id: string): string {
  if (id === 'period') return 'period';
  return catalog?.breakdowns.find((b) => b.id === id)?.kind ?? (['customer', 'product', 'distributor'].includes(id) ? 'entity' : 'attribute');
}

/** Entity breakdowns take ids as filter values; everything else takes the value itself. */
export function isEntityBreakdown(catalog: CatalogV2 | null | undefined, id: string): boolean {
  return breakdownKind(catalog, id) === 'entity';
}

/** Chart / format unit of a v2 unit. Governed measures (unit null) use the Reports page's table. */
export function chartUnit(unit: V2Unit | null | undefined, governedKey?: string | null): MeasureUnit {
  switch (unit) {
    case 'units':
    case 'units_per_week':
      return 'units';
    case 'count':
      return 'count';
    case 'usd':
    case 'usd_per_unit':
      return 'usd';
    case 'zar':
      return 'zar';
    case 'ratio':
      return 'percent';
    default:
      return governedKey ? metricPresentation({ key: governedKey, formula: '' }).unit : 'number';
  }
}

export function measureUnit(m: V2Measure | undefined): MeasureUnit {
  if (!m) return 'number';
  return chartUnit(m.unit, m.kind === 'governed' ? m.legacy_key ?? m.id : null);
}

/** Adds up across rows (stack, pie). Governed metrics use the Reports page's table. */
export function isAdditive(m: V2Measure | undefined): boolean {
  if (!m) return false;
  if (m.kind === 'governed') return Boolean(metricPresentation({ key: m.legacy_key ?? m.id, formula: '' }).additive);
  return m.additivity === 'additive';
}

export function isRatio(m: V2Measure | undefined): boolean {
  return m?.unit === 'ratio' || measureUnit(m) === 'percent';
}

/** Short tag of a model for filter options: who the customer is in that model (spec s.3). */
export function customerRoleTag(model: V2Model | undefined): string {
  if (!model) return '';
  if (model.id === 'dsi_sellout') return 'Dealer (DSI)';
  if (model.id === 'cst_sellthrough') return 'Retailer (CST)';
  if (model.id === 'cpor') return 'CPOR account';
  return model.label;
}

/** Measures a governed metric can be picked as: handler-backed, not refused outright. */
export function isPickableGoverned(m: V2Measure): boolean {
  return m.kind === 'governed' && m.handler_backed !== false && !m.refuse_all && (m.status == null || m.status === 'implemented');
}
