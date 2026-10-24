'use client';

/**
 * Values for a filter picker, from v2 execute itself (spec s.3; no new endpoint): for each model on
 * the dashboard that has the breakdown, `{measures: [<model>.lines], breakdowns: [key], period:
 * <window>, sort lines desc, limit 5000}`, combined by id. Only values with data in the window are
 * listed. Names only; each customer option says which model it comes from (a DSI dealer and a CST
 * retailer can share an id).
 */

import { useQueries } from '@tanstack/react-query';
import { useMemo } from 'react';

import { useV2Executor } from './BuilderData';
import { customerRoleTag, modelOf } from './catalog';
import { breakdownColumns, catOf } from './shape';
import type { CatalogV2, DateWindow, V2FilterValue, V2Request, V2Response } from './types';

export type FilterOption = { value: V2FilterValue; label: string; tags: string[] };

export const OPTIONS_LIMIT = 5000;

/** Models whose values a picker lists: the dashboard's models with that breakdown, else every model with it. */
export function optionModels(catalog: CatalogV2 | null | undefined, key: string, dashboardModels: string[]): string[] {
  const withKey = (catalog?.models ?? []).filter((m) => m.breakdowns.includes(key)).map((m) => m.id);
  const used = withKey.filter((m) => dashboardModels.includes(m));
  return used.length ? used : withKey;
}

export function optionsRequest(catalog: CatalogV2 | null | undefined, modelId: string, key: string, window: DateWindow): V2Request | null {
  const lines = `${modelId}.lines`;
  const measure = catalog?.measures.find((m) => m.id === lines) ?? catalog?.measures.find((m) => m.model === modelId && m.kind === 'base' && m.additivity === 'additive');
  if (!measure) return null;
  const req: V2Request = { measures: [measure.id], breakdowns: [key], sort: { by: measure.id, dir: 'desc' }, limit: OPTIONS_LIMIT };
  if (window) req.period = { from: window.from, to: window.to };
  return req;
}

/** Combine per-model answers into one option list by value (names, model tags). */
export function combineOptions(catalog: CatalogV2 | null | undefined, key: string, answers: { modelId: string; resp: V2Response | undefined }[]): FilterOption[] {
  const by = new Map<string, FilterOption>();
  for (const { modelId, resp } of answers) {
    if (!resp?.ok) continue;
    const col = breakdownColumns(resp).find((c) => c.id === key);
    if (!col) continue;
    const tag = key === 'customer' ? customerRoleTag(modelOf(catalog, modelId)) : '';
    for (const row of resp.rows) {
      const cat = catOf(row, col);
      if (cat.value == null) continue; // an entity with no id cannot be picked
      const k = String(cat.value);
      const opt = by.get(k) ?? { value: cat.value, label: cat.label, tags: [] };
      if (tag && !opt.tags.includes(tag)) opt.tags.push(tag);
      by.set(k, opt);
    }
  }
  return [...by.values()].sort((a, b) => a.label.localeCompare(b.label, 'en', { sensitivity: 'base', numeric: true }));
}

export function useFilterOptions(
  catalog: CatalogV2 | null | undefined,
  key: string,
  dashboardModels: string[],
  window: DateWindow,
  enabled: boolean,
): { options: FilterOption[]; loading: boolean; truncated: boolean } {
  const execute = useV2Executor();
  const models = useMemo(() => optionModels(catalog, key, dashboardModels), [catalog, key, dashboardModels]);
  const results = useQueries({
    queries: models.map((modelId) => {
      const req = optionsRequest(catalog, modelId, key, window);
      return {
        queryKey: ['v2-filter-options', modelId, key, req],
        queryFn: ({ signal }: { signal: AbortSignal }) => execute(req as V2Request, signal),
        enabled: enabled && Boolean(req),
        staleTime: 5 * 60_000,
        retry: false,
      };
    }),
  });
  const answers = models.map((modelId, i) => ({ modelId, resp: results[i]?.data as V2Response | undefined }));
  // Recombine only when an answer changes (5,000 rows per model is too many to redo every render).
  const stamp = results.map((r) => r.dataUpdatedAt).join('|');
  // eslint-disable-next-line react-hooks/exhaustive-deps
  const options = useMemo(() => combineOptions(catalog, key, answers), [catalog, key, models.join('|'), stamp]);
  return {
    options,
    loading: results.some((r) => r.isLoading && r.fetchStatus !== 'idle'),
    truncated: answers.some((a) => a.resp?.truncated),
  };
}
