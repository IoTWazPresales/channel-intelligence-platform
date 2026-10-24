/**
 * What a card needs from its dashboard to run: the effective filters (bar AND click chips), the
 * window, the comparison window, required filters, value names for messages, and the click handler.
 */

import type { SelectDatum } from './clickFilters';
import type { FilterSelection, ValueNames } from './requestFor';
import type { DateWindow } from './types';

export type DashboardRunContext = {
  filters: FilterSelection;
  window: DateWindow;
  /** The KPI comparison window (null: no comparison). */
  compare: DateWindow;
  /** "previous period" / "previous year". */
  compareLabel?: string;
  required?: string[];
  names?: ValueNames;
  /** Active chip keys ("customer:18", "period:2026-W14"). */
  selectedKeys: string[];
  onSelect?: (d: SelectDatum, additive: boolean) => void;
  /** Clears the bar's values and the chips (empty-state "Clear filters"). */
  onClearFilters?: () => void;
  hasActiveFilters: boolean;
  /** One line for exports: "Customer: Makro · 2026-07-01 to 2026-10-09". */
  filterCaption: string;
  /** Empty state: "in the last 13 weeks" / "for Makro in the last 13 weeks". */
  emptyContext?: string;
};

export const NO_FILTERS: DashboardRunContext = {
  filters: {},
  window: null,
  compare: null,
  selectedKeys: [],
  hasActiveFilters: false,
  filterCaption: 'All time, no filters',
};
