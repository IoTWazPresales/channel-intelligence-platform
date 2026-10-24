/**
 * Click to filter (spec s.5, S10): session chips, never saved.
 *
 * - A click sets that breakdown's chip to the clicked value; clicking the same value again removes it.
 * - Ctrl/Cmd-click adds or removes one value and keeps the others.
 * - A period click narrows the dates to that bucket; clearing it restores the bar's own range.
 * - "Unassigned" for an entity (no id) is not filterable: the v2 filter takes ids.
 * - Chips AND with the bar: on the same key the widget gets the intersection (a narrowing click).
 */

import { compareWindow } from './dates';
import type { FilterSelection } from './requestFor';
import type { CompareMode, DashboardFilters, DateWindow, V2FilterValue } from './types';

export type Chip = { key: string; value: V2FilterValue; label: string };

export type ClickState = { chips: Chip[]; period: { label: string; window: { from: string; to: string } } | null };

export const EMPTY_CLICKS: ClickState = { chips: [], period: null };

/** What a chart mark hands back on click. `value: null` = an entity with no id (not filterable). */
export type SelectDatum = {
  breakdown: string;
  value: V2FilterValue | null;
  label: string;
  /** Period marks: the bucket's dates. */
  window?: { from: string; to: string } | null;
};

export type ClickAction =
  | { type: 'select'; datum: SelectDatum; additive?: boolean }
  | { type: 'remove'; key: string; value: V2FilterValue }
  | { type: 'clearPeriod' }
  | { type: 'clear' };

const same = (a: V2FilterValue, b: V2FilterValue) => String(a) === String(b);

export function isSelectable(d: SelectDatum): boolean {
  if (d.breakdown === 'period') return Boolean(d.window);
  return d.value != null;
}

export function clickReducer(state: ClickState, action: ClickAction): ClickState {
  switch (action.type) {
    case 'clear':
      return EMPTY_CLICKS;
    case 'clearPeriod':
      return { ...state, period: null };
    case 'remove':
      return { ...state, chips: state.chips.filter((c) => !(c.key === action.key && same(c.value, action.value))) };
    case 'select': {
      const d = action.datum;
      if (!isSelectable(d)) return state;
      if (d.breakdown === 'period') {
        const w = d.window!;
        if (state.period && state.period.window.from === w.from && state.period.window.to === w.to) return { ...state, period: null };
        return { ...state, period: { label: d.label, window: { from: w.from, to: w.to } } };
      }
      const value = d.value as V2FilterValue;
      const has = state.chips.some((c) => c.key === d.breakdown && same(c.value, value));
      const chip: Chip = { key: d.breakdown, value, label: d.label };
      if (action.additive) {
        return {
          ...state,
          chips: has ? state.chips.filter((c) => !(c.key === d.breakdown && same(c.value, value))) : [...state.chips, chip],
        };
      }
      const ofKey = state.chips.filter((c) => c.key === d.breakdown);
      const others = state.chips.filter((c) => c.key !== d.breakdown);
      if (has && ofKey.length === 1) return { ...state, chips: others };
      return { ...state, chips: [...others, chip] };
    }
    default:
      return state;
  }
}

/** The bar's value filters (the saved keys, plus any other breakdown key with a list). */
export function barSelection(bar: Partial<DashboardFilters> | null | undefined): FilterSelection {
  const out: FilterSelection = {};
  for (const [k, v] of Object.entries(bar ?? {})) {
    if (k === 'date' || k === 'compare' || k === 'required') continue;
    if (Array.isArray(v)) {
      const vals = v.filter((x): x is V2FilterValue => typeof x === 'string' || typeof x === 'number');
      if (vals.length) out[k] = vals;
    }
  }
  return out;
}

/** Bar AND chips: chips narrow the bar's values on the same key, and add keys the bar lacks. */
export function effectiveSelection(bar: FilterSelection, clicks: ClickState): FilterSelection {
  const out: FilterSelection = { ...bar };
  const byKey = new Map<string, V2FilterValue[]>();
  for (const c of clicks.chips) byKey.set(c.key, [...(byKey.get(c.key) ?? []), c.value]);
  for (const [k, vals] of byKey) {
    const barVals = bar[k];
    // An explicit empty list means an impossible selection, not an absent filter.
    out[k] = barVals ? barVals.filter((x) => vals.some((y) => same(x, y))) : vals;
  }
  return out;
}

/** The window the widgets run: a period chip, else the bar's preset. */
export function effectiveWindow(barWindow: DateWindow, clicks: ClickState): DateWindow {
  return clicks.period ? clicks.period.window : barWindow;
}

export function effectiveCompare(window: DateWindow, mode: CompareMode | undefined): DateWindow {
  return compareWindow(window, mode);
}
