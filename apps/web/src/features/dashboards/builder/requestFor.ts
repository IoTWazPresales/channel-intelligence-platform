/**
 * One widget's v2 request under the dashboard's filters (spec s.3, API report s.4.5).
 *
 * - Model measures: a dashboard filter applies only when the model has that breakdown. Otherwise it
 *   is NOT sent (the planner would refuse the whole query) and the widget says so in plain words,
 *   with the catalog's own `filter_refusals` text.
 * - Governed measures: a filter applies only when the handler reads it (`honours.filters`) and has
 *   exactly one value; dates only when `honours.dates && !honours.all_time_only`.
 * - The widget's own filters AND with the dashboard's: on the same key the request carries the
 *   intersection; an empty intersection runs no query.
 * - A required filter with no value runs no query.
 */

import { breakdownLabel, definitionKind, lowerFirst, measureOf, modelOf } from './catalog';
import { isoDay, parseDay, windowLabel } from './dates';
import type { CatalogV2, DateWindow, DefinitionV2, V2FilterValue, V2Measure, V2Request } from './types';

/** Breakdown id -> chosen values; an explicit empty list means an empty intersection. */
export type FilterSelection = Record<string, V2FilterValue[]>;

/** Breakdown id -> value -> display name (for plain-words messages; never an id code). */
export type ValueNames = Record<string, Record<string, string>>;

export type NotFiltered = { key: string; label: string; reason: string };

export type RequestPlan =
  | {
      status: 'ready';
      request: V2Request;
      notFiltered: NotFiltered[];
      /** Filter keys actually sent. */
      applied: string[];
      /** The window sent (null: none). */
      window: DateWindow;
      kind: 'model' | 'governed';
      /** Plain caption to show under a figure (latest-stock measures), with `{to}` filled. */
      caption?: string;
      /** Names/counts and dates of filters actually applied, including widget-only restrictions. */
      filterCaption: string;
    }
  | { status: 'blocked'; reason: 'required' | 'empty_intersection' | 'no_measure' | 'catalog_unavailable' | 'invalid_window' | 'invalid_filter'; message: string; notFiltered: NotFiltered[] };

export type RequestContext = {
  catalog: CatalogV2 | null | undefined;
  filters: FilterSelection;
  window: DateWindow;
  required?: string[];
  names?: ValueNames;
};

function asList(v: unknown): V2FilterValue[] {
  if (v == null) return [];
  if (Array.isArray(v)) return v.filter((x): x is V2FilterValue => typeof x === 'string' || typeof x === 'number');
  return typeof v === 'string' || typeof v === 'number' ? [v] : [];
}

function sameValue(a: V2FilterValue, b: V2FilterValue): boolean {
  return String(a) === String(b);
}

export function intersect(a: V2FilterValue[], b: V2FilterValue[]): V2FilterValue[] {
  return a.filter((x) => b.some((y) => sameValue(x, y)));
}

const WALL_FOR_HANDLER: Record<string, string> = { a3_stock: 'W-A3-GRAIN-LOCK', a1_pve: 'W-PVE-GRAIN' };

function sentence(reason: string): string {
  const t = lowerFirst(reason.trim());
  return /[.!?]$/.test(t) ? t : `${t}.`;
}

/** Why a governed metric is not filtered by `key` (the handler does not read it). */
function governedFilterReason(catalog: CatalogV2 | null | undefined, m: V2Measure): string {
  const handler = m.honours?.handler ?? null;
  if (!m.honours) return 'this server does not say which filters this metric reads, so none are sent.';
  const wallId = handler ? WALL_FOR_HANDLER[handler] : undefined;
  const wall = wallId ? catalog?.walls.find((w) => w.id === wallId) : undefined;
  if (wall) return sentence(wall.reason);
  return 'the figure is worked out without it.';
}

function governedDateReason(m: V2Measure): string {
  const h = m.honours;
  if (h?.all_time_only) return 'this metric is worked out over all time, so the date range does not change it.';
  if (h?.handler === 'a3_stock') return 'stock is the latest count, so the date range does not change it.';
  return 'the figure is worked out without dates.';
}

function namesFor(names: ValueNames | undefined, key: string, values: V2FilterValue[]): string | null {
  const map = names?.[key];
  if (!map) return null;
  const out = values.map((v) => map[String(v)]).filter(Boolean);
  if (out.length !== values.length || !out.length) return null;
  return out.length <= 3 ? out.join(', ') : `${out.slice(0, 3).join(', ')} and ${out.length - 3} more`;
}

export function validFixedWindow(window: NonNullable<DateWindow>): boolean {
  const from = parseDay(window.from);
  const to = parseDay(window.to);
  return Boolean(from && to && isoDay(from) === window.from && isoDay(to) === window.to && window.from <= window.to);
}

export function requestFor(def: DefinitionV2, ctx: RequestContext): RequestPlan {
  const { catalog } = ctx;
  const notFiltered: NotFiltered[] = [];
  const measures = def.query.measures ?? [];
  if (!measures.length) return { status: 'blocked', reason: 'no_measure', message: 'Pick a measure.', notFiltered };
  if (!catalog || measures.some((id) => {
    const measure = measureOf(catalog, id);
    return !measure || (measure.kind !== 'governed' && !modelOf(catalog, measure.model));
  })) {
    return { status: 'blocked', reason: 'catalog_unavailable', message: 'The data model for this widget is unavailable. Reload the data model before running or editing it.', notFiltered };
  }

  const ignored = new Set(def.dashboard?.ignore_filters ?? []);
  const fixed = def.dashboard?.fixed_window;
  if (fixed && !validFixedWindow(fixed)) {
    return { status: 'blocked', reason: 'invalid_window', message: 'Choose valid fixed dates with the start on or before the end.', notFiltered };
  }
  for (const key of ignored) {
    if (key === 'date' && fixed) continue;
    notFiltered.push({ key, label: key === 'date' ? 'Date' : breakdownLabel(catalog, key), reason: 'this widget explicitly ignores this dashboard filter.' });
  }
  if (fixed) notFiltered.push({ key: 'date', label: 'Date', reason: `this widget uses fixed dates, ${fixed.from} to ${fixed.to}.` });
  const requestedWindow = fixed ?? (ignored.has('date') ? null : ctx.window);

  // Required bar filters still apply unless the widget explicitly opts out.
  for (const key of ctx.required ?? []) {
    if (ignored.has(key)) continue;
    if (!(ctx.filters[key]?.length ?? 0)) {
      const label = lowerFirst(breakdownLabel(catalog, key));
      const what = key === 'customer' ? 'this account' : 'this dashboard';
      return { status: 'blocked', reason: 'required', message: `Pick a ${label} above to see ${what}.`, notFiltered };
    }
  }

  const kind = definitionKind(catalog, def);
  const first = measureOf(catalog, measures[0]);
  const model = kind === 'model' ? modelOf(catalog, first?.model) : undefined;
  const filters: Record<string, V2FilterValue | V2FilterValue[]> = {};
  const applied: string[] = [];

  // Dashboard filters.
  const dash: FilterSelection = {};
  for (const [key, raw] of Object.entries(ctx.filters)) {
    if (ignored.has(key)) continue;
    const values = asList(raw);
    if (key === 'period') continue;
    const label = breakdownLabel(catalog, key);
    const applies = kind === 'model' ? model?.breakdowns.includes(key) : first?.honours?.filters.includes(key);
    if (!values.length && Array.isArray(raw) && applies) {
      return {
        status: 'blocked', reason: 'empty_intersection',
        message: `The dashboard and chart selections have no ${lowerFirst(label)} in common. Clear a selection to see this figure.`,
        notFiltered,
      };
    }
    if (!values.length) continue;
    if (kind === 'model') {
      if (model && model.breakdowns.includes(key)) {
        dash[key] = values;
      } else {
        const reason = model?.filter_refusals?.[key] ?? `${label} is not a breakdown of ${model?.label ?? 'this data'}.`;
        notFiltered.push({ key, label, reason: sentence(reason) });
      }
    } else if (first) {
      const reads = first.honours?.filters ?? [];
      if (!reads.includes(key)) {
        notFiltered.push({ key, label, reason: governedFilterReason(catalog, first) });
      } else if (values.length !== 1) {
        notFiltered.push({ key, label, reason: `this metric takes one ${lowerFirst(label)} at a time.` });
      } else {
        dash[key] = values;
      }
    }
  }

  // The widget's own filters, ANDed: intersection on the same key.
  const own = def.query.filters ?? {};
  for (const [key, raw] of Object.entries(own)) {
    // The model API accepts JSON null, but the builder's picker/value types do not yet represent
    // it. Refuse the saved question rather than drop its restriction or substitute a text value.
    if (raw === null || (Array.isArray(raw) && raw.some((value) => value === null))) {
      return {
        status: 'blocked', reason: 'invalid_filter',
        message: `This widget's ${lowerFirst(breakdownLabel(catalog, key))} filter includes a missing value. This builder cannot run or promote filters for missing values yet.`,
        notFiltered,
      };
    }
    const values = asList(raw);
    if (!values.length) continue;
    if (dash[key]) {
      const both = intersect(values, dash[key]);
      if (!both.length) {
        const who = namesFor(ctx.names, key, values) ?? `its own ${lowerFirst(breakdownLabel(catalog, key))} filter`;
        return {
          status: 'blocked',
          reason: 'empty_intersection',
          message: `This widget is limited to ${who}, which the dashboard filter leaves out.`,
          notFiltered,
        };
      }
      dash[key] = both;
    } else {
      dash[key] = values;
    }
  }

  for (const [key, values] of Object.entries(dash)) {
    // Governed handlers take one scalar value; model filters take a list.
    filters[key] = kind === 'governed' ? values[0] : values;
    applied.push(key);
  }

  // Dates.
  let window: DateWindow = null;
  if (requestedWindow) {
    if (kind === 'model') {
      window = requestedWindow;
    } else if (first?.honours?.dates && !first.honours.all_time_only) {
      window = requestedWindow;
    } else if (first) {
      if (fixed) return { status: 'blocked', reason: 'invalid_window', message: 'This metric cannot use fixed dates. Follow the dashboard dates instead.', notFiltered };
      notFiltered.push({ key: 'date', label: 'Date', reason: governedDateReason(first) });
    }
  }

  const request: V2Request = { measures: [...measures] };
  const breakdowns = def.query.breakdowns ?? [];
  if (breakdowns.length) request.breakdowns = [...breakdowns];
  const grain = def.query.period?.grain ?? null;
  if (grain || window) {
    request.period = {};
    if (grain) request.period.grain = grain;
    if (window) {
      request.period.from = window.from;
      request.period.to = window.to;
    }
  }
  if (Object.keys(filters).length) request.filters = filters;
  if (def.query.sort) request.sort = { ...def.query.sort };
  if (def.query.limit) request.limit = def.query.limit;

  // Latest-stock measures read the window as "latest report on or before `to`".
  let caption: string | undefined;
  const template = def.display?.caption;
  if (template) caption = template.replace('{to}', window?.to ?? 'today');
  else if (kind === 'model' && measures.some((id) => measureOf(catalog, id)?.additivity === 'semi_additive')) {
    caption = `Latest report on or before ${window?.to ?? 'today'}.`;
  }

  const filterCaption = [...applied.map((key) => `${breakdownLabel(catalog, key)}: ${namesFor(ctx.names, key, dash[key]) ?? `${dash[key].length} selected`}`), windowLabel(window)].join(' · ');
  return { status: 'ready', request, notFiltered, applied, window, kind, caption, filterCaption };
}

/** "Not filtered by distributor, store / site" (keys in order, labels in lower case). */
export function notFilteredHeadline(items: NotFiltered[]): string | null {
  if (!items.length) return null;
  if (items.length === 1) return `Not filtered by ${lowerFirst(items[0].label)}: ${items[0].reason}`;
  return `Not filtered by ${items.map((i) => lowerFirst(i.label)).join(', ')}`;
}

/** The same request over another window (KPI compare) or at a period grain (sparkline). */
export function withWindow(req: V2Request, window: DateWindow): V2Request {
  const next: V2Request = { ...req, period: { ...(req.period ?? {}) } };
  if (window) {
    next.period!.from = window.from;
    next.period!.to = window.to;
  } else {
    delete next.period!.from;
    delete next.period!.to;
  }
  if (!next.period!.grain && !next.period!.from) delete next.period;
  return next;
}

/** The KPI's trend: its first measure by period (no grain for a governed metric with no calendar grain). */
export function sparklineRequest(req: V2Request, grain: string | null): V2Request {
  const period = { ...(req.period ?? {}) };
  if (grain) period.grain = grain;
  else delete period.grain;
  const out: V2Request = { measures: [req.measures[0]], breakdowns: ['period'], limit: 500 };
  if (period.grain || period.from) out.period = period;
  if (req.filters) out.filters = req.filters;
  return out;
}

/** Breakdowns for "View rows": the widget's own, filled to 3 with the model's finest (spec s.5). */
export const FINEST_BREAKDOWNS: Record<string, string[]> = {
  dsi_sellout: ['customer', 'product', 'period'],
  cst_sellthrough: ['customer', 'product', 'site_label', 'period'],
  cpor: ['case', 'customer', 'product', 'status'],
};

export function viewRowsBreakdowns(own: string[], modelId: string | null | undefined, allowed: string[], max = 3): string[] {
  const out = [...own];
  for (const b of FINEST_BREAKDOWNS[modelId ?? ''] ?? []) {
    if (out.length >= max) break;
    if (!out.includes(b) && allowed.includes(b)) out.push(b);
  }
  return out.slice(0, max);
}
