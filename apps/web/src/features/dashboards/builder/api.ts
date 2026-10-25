/**
 * API client for the N-0116 builder. Every route the live API may not have yet (an API without
 * migration 0048) degrades instead of failing: a missing catalog or template list reads as `null`,
 * and a missing layout route falls back to the old full PUT of the widget list.
 */

import { apiGet, apiPatch, apiPost, apiPut } from '@/lib/api';

import type { Dashboard, DashboardWidget } from '../types';
import type { CatalogV2, DashboardFilters, DefinitionV2, TemplatesResponse, V2Request, V2Response } from './types';

/** A route the server does not have: 404 / 405 (FastAPI JSON or a proxy page). */
export function isMissingRouteError(e: unknown): boolean {
  const msg = e instanceof Error ? e.message : typeof e === 'string' ? e : '';
  return /\((404|405)\)/.test(msg) || /^(Not Found|Method Not Allowed)$/i.test(msg.trim());
}

/** The v2 catalog, or `null` when the server has no v2 catalog (the builder then offers the v1 editor). */
export async function fetchCatalogV2(signal?: AbortSignal): Promise<CatalogV2 | null> {
  try {
    return await apiGet<CatalogV2>('/api/v1/semantics/v2/catalog', { signal });
  } catch (e) {
    if (isMissingRouteError(e)) return null;
    throw e;
  }
}

export function executeV2(req: V2Request, signal?: AbortSignal): Promise<V2Response> {
  return apiPost<V2Response>('/api/v1/query/v2/execute', req, { signal });
}

/**
 * The starters, or `null` when the server has none (starters are then hidden). On an API before 0048
 * `/dashboards/templates` falls into `GET /dashboards/{id}` and fails int validation (422), so any
 * failure reads as "no starters": the list is optional, never a reason to break the page.
 */
export async function fetchTemplates(signal?: AbortSignal): Promise<TemplatesResponse | null> {
  try {
    const r = await apiGet<TemplatesResponse>('/api/v1/dashboards/templates', { signal });
    return r && Array.isArray(r.items) ? r : null;
  } catch (e) {
    if (signal?.aborted) throw e;
    return null;
  }
}

export function createFromTemplate(key: string, name?: string): Promise<Dashboard> {
  return apiPost<Dashboard>('/api/v1/dashboards/from-template', name ? { key, name } : { key });
}

export function saveDashboardFilters(dashboardId: number, filters: DashboardFilters): Promise<Dashboard> {
  return apiPatch<Dashboard>(`/api/v1/dashboards/${dashboardId}`, { filters_json: filters });
}

export type LayoutItem = { id: number; x: number; y: number; w: number; h: number };

/** The old full replace: every widget's v1 fields, as the page sent before N-0116. */
function legacyWidgetsBody(dashboard: Dashboard, layout: LayoutItem[]) {
  const byId = new Map(layout.map((l) => [l.id, { x: l.x, y: l.y, w: l.w, h: l.h }]));
  return {
    widgets: (dashboard.widgets ?? []).map((w, i) => ({
      id: w.id,
      title: w.title,
      visual: w.visual,
      metric_key: w.metric_key,
      grains: w.grains,
      filters: w.filters,
      period_grain: w.period_grain,
      layout_json: byId.get(w.id) ?? w.layout_json,
      saved_report_id: w.saved_report_id,
      sort_order: i,
      // A server that knows definition_v2 keeps it when it is sent back unchanged.
      ...(w.definition_v2 ? { definition_v2: w.definition_v2 } : {}),
    })),
  };
}

/**
 * Save drag / resize: `PATCH /dashboards/{id}/layout` writes only the positions. A server without that
 * route (404 / 405) gets the old `PUT /widgets` with every widget, as before.
 */
export async function persistLayout(dashboard: Dashboard, layout: LayoutItem[]): Promise<{ dashboard: Dashboard; route: 'patch' | 'put' }> {
  try {
    const d = await apiPatch<Dashboard>(`/api/v1/dashboards/${dashboard.id}/layout`, layout);
    return { dashboard: d, route: 'patch' };
  } catch (e) {
    if (!isMissingRouteError(e)) throw e;
    const d = await apiPut<Dashboard>(`/api/v1/dashboards/${dashboard.id}/widgets`, legacyWidgetsBody(dashboard, layout));
    return { dashboard: d, route: 'put' };
  }
}

export type WidgetV2Body = {
  title: string;
  visual: DashboardWidget['visual'];
  definition_v2: DefinitionV2;
  layout_json?: { x: number; y: number; w: number; h: number };
};

export function createWidgetV2(dashboardId: number, body: WidgetV2Body): Promise<Dashboard> {
  return apiPost<Dashboard>(`/api/v1/dashboards/${dashboardId}/widgets`, body);
}

export function patchWidgetV2(dashboardId: number, widgetId: number, body: Partial<WidgetV2Body>): Promise<Dashboard> {
  return apiPatch<Dashboard>(`/api/v1/dashboards/${dashboardId}/widgets/${widgetId}`, body);
}

/** Duplicate: same definition (or v1 fields), "(copy)", placed below every widget. */
export function duplicateBody(dashboard: Dashboard, w: DashboardWidget) {
  const l = w.layout_json ?? {};
  const bottom = Math.max(0, ...(dashboard.widgets ?? []).map((x) => (x.layout_json?.y ?? 0) + (x.layout_json?.h ?? 8)));
  const layout_json = { x: typeof l.x === 'number' ? l.x : 0, y: bottom, w: typeof l.w === 'number' ? l.w : 6, h: typeof l.h === 'number' ? l.h : 8 };
  const title = `${w.title} (copy)`;
  if (w.definition_v2) {
    const { v, kind, query, display, dashboard } = w.definition_v2;
    return { title, visual: w.visual, definition_v2: { v, kind, query, ...(display ? { display } : {}), ...(dashboard ? { dashboard } : {}) }, layout_json };
  }
  return { title, visual: w.visual, metric_key: w.metric_key, grains: w.grains, period_grain: w.period_grain, filters: w.filters, layout_json };
}
