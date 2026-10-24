'use client';

import { useEffect, useMemo, useReducer, useState, useCallback } from 'react';

import { breakdownLabel } from './catalog';
import { EMPTY_CLICKS, barSelection, clickReducer, effectiveSelection, effectiveWindow, type ClickAction, type ClickState } from './clickFilters';
import { compareWindow, DATE_PRESETS, resolvePreset } from './dates';
import type { ValueNames } from './requestFor';
import type { DashboardRunContext } from './runContext';
import type { CatalogV2, DashboardFilters, DateWindow } from './types';

function periodPhrase(f: DashboardFilters, clicks: ClickState, window: DateWindow): string {
  if (clicks.period) return `in ${clicks.period.label}`;
  const p = f.date.preset;
  if (p === 'all_time' || !window) return '';
  if (p === 'custom') return `from ${window.from} to ${window.to}`;
  const label = DATE_PRESETS.find((d) => d.id === p)?.label ?? '';
  return p === 'this_year' ? 'this year' : `in the ${label.toLowerCase()}`;
}

export function buildRunContext(args: {
  catalog: CatalogV2 | null | undefined;
  bar: DashboardFilters;
  clicks: ClickState;
  names: ValueNames;
  dispatch?: (a: ClickAction) => void;
  onClearBar?: () => void;
  now?: Date;
}): DashboardRunContext {
  const { catalog, bar, clicks, names } = args;
  const filters = effectiveSelection(barSelection(bar), clicks);
  const window = effectiveWindow(resolvePreset(bar.date, args.now), clicks);
  const compare = compareWindow(window, bar.compare);
  const selectedKeys = [...clicks.chips.map((c) => `${c.key}:${c.value}`), ...(clicks.period ? [`period:${clicks.period.label}`] : [])];
  const parts: string[] = [];
  let forWho = '';
  for (const [k, vals] of Object.entries(filters)) {
    const ns = vals.map((v) => names[k]?.[String(v)] ?? clicks.chips.find((c) => c.key === k && String(c.value) === String(v))?.label).filter(Boolean) as string[];
    const shown = ns.length === vals.length ? ns.join(', ') : `${vals.length} selected`;
    parts.push(`${breakdownLabel(catalog, k)}: ${shown}`);
    if (!forWho && ns.length === vals.length && ns.length <= 2) forWho = `for ${ns.join(' and ')}`;
  }
  const when = window ? `${window.from} to ${window.to}` : 'All time';
  const phrase = periodPhrase(bar, clicks, window);
  return {
    filters,
    window,
    compare,
    compareLabel: bar.compare === 'previous_year' ? 'previous year' : bar.compare === 'previous_period' ? 'previous period' : undefined,
    required: bar.required,
    names,
    selectedKeys,
    onSelect: args.dispatch ? (datum, additive) => args.dispatch!({ type: 'select', datum, additive }) : undefined,
    onClearFilters: () => {
      args.dispatch?.({ type: 'clear' });
      args.onClearBar?.();
    },
    hasActiveFilters: Object.keys(filters).length > 0 || window != null,
    filterCaption: [...parts, when].join(' · '),
    emptyContext: [forWho, phrase].filter(Boolean).join(' ') || undefined,
  };
}

/** Bar state, click chips (Esc clears them) and the names the pickers have seen. */
export function useDashboardRun(catalog: CatalogV2 | null | undefined, bar: DashboardFilters, onClearBar?: () => void, dashboardId?: string | number | null) {
  const [clicks, dispatch] = useReducer(clickReducer, EMPTY_CLICKS);
  const [names, setNames] = useState<ValueNames>({});
  const [scope, setScope] = useState(dashboardId);
  // Reset during rendering so children never commit a query for the new dashboard with old chips.
  // A widget-save refetch retains the same id and must preserve the user's session selection.
  if (scope !== dashboardId) {
    setScope(dashboardId);
    dispatch({ type: 'clear' });
    setNames({});
  }
  const addNames = useCallback((key: string, map: Record<string, string>) => {
    setNames((old) => {
      const prev = old[key] ?? {};
      const keys = Object.keys(map);
      if (keys.every((k) => prev[k] === map[k])) return old;
      return { ...old, [key]: { ...prev, ...map } };
    });
  }, []);
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== 'Escape') return;
      // Esc inside a dialog, menu or picker belongs to that control.
      const t = e.target as HTMLElement | null;
      if (t?.closest?.('[role="dialog"], [role="menu"], [role="listbox"], [role="combobox"]')) return;
      dispatch({ type: 'clear' });
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, []);
  const ctx = useMemo(
    () => buildRunContext({ catalog, bar, clicks, names, dispatch, onClearBar }),
    [catalog, bar, clicks, names, onClearBar],
  );
  return { ctx, clicks, dispatch, addNames };
}
