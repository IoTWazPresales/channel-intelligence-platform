'use client';

/**
 * Optional columns for a Tier A fact grid (N-0034). The field list comes from the API registry
 * (`GET /api/v1/grid-fields/{gridId}`), so the list and the row payload share one source; this hook
 * owns the fetch, the per-grid localStorage layout (read / write / prune) and the generic formatter.
 * Render the picker with `<FactColumnPicker {...pickerProps} />` (features/workbench-ui/FactColumnPicker).
 */

import { useQuery } from '@tanstack/react-query';
import type { ColDef, ValueFormatterParams } from 'ag-grid-community';
import { useCallback, useEffect, useMemo, useState } from 'react';

import { fmtCellForKey } from '@/app/(app)/shipping/shippingGridFormatters';
import { apiGet } from '@/lib/api';

export type GridFieldItem = {
  field: string;
  label: string;
  group: 'fact' | 'reference';
  default_hidden: boolean;
};

export type FactColumnPickerProps = {
  open: boolean;
  onClose: () => void;
  gridId: string;
  items: GridFieldItem[];
  selected: string[];
  onToggle: (field: string, visible: boolean) => void;
  onReset: () => void;
  gridReady: boolean;
  loading: boolean;
};

export type UseFactColumnsOptions<T> = {
  /** Existing localStorage key to keep (inbound shipments); default `cip.grid.<gridId>.optional.v1`. */
  storageKey?: string;
  /** Per-field display formatter; default formats dates and JSON like the inbound grid. */
  formatters?: Record<string, (value: unknown) => string>;
  /** Extra ColDef props per optional field (width, wrap). */
  colDefFor?: (field: string) => Partial<ColDef<T>>;
};

export function gridLayoutStorageKey(gridId: string): string {
  return `cip.grid.${gridId}.optional.v1`;
}

type StoredLayout = { optionalFields?: unknown } & Record<string, unknown>;

function readStored(key: string): StoredLayout | null {
  try {
    const raw = localStorage.getItem(key);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as unknown;
    return parsed && typeof parsed === 'object' && !Array.isArray(parsed) ? (parsed as StoredLayout) : null;
  } catch {
    return null;
  }
}

/** Merge `optionalFields` into the stored object so other keys (inbound's pageSize) survive. */
function writeStored(key: string, optionalFields: string[]): void {
  try {
    const prev = readStored(key) ?? {};
    localStorage.setItem(key, JSON.stringify({ ...prev, optionalFields }));
  } catch {
    /* storage unavailable (private window, quota): the layout just does not persist */
  }
}

export function useFactColumns<T>(gridId: string, opts: UseFactColumnsOptions<T> = {}) {
  const storageKey = opts.storageKey ?? gridLayoutStorageKey(gridId);
  const { formatters, colDefFor } = opts;
  const [open, setOpen] = useState(false);
  const [selected, setSelected] = useState<string[]>([]);
  const [persistReady, setPersistReady] = useState(false);

  const { data, isLoading, isSuccess } = useQuery({
    queryKey: ['grid-fields', gridId],
    queryFn: ({ signal }) =>
      apiGet<{ items?: GridFieldItem[] }>(`/api/v1/grid-fields/${encodeURIComponent(gridId)}`, { signal }),
    staleTime: 5 * 60_000,
  });
  const items = useMemo(() => (Array.isArray(data?.items) ? data.items : []), [data]);

  useEffect(() => {
    const stored = readStored(storageKey);
    if (stored && Array.isArray(stored.optionalFields)) {
      setSelected(stored.optionalFields.filter((f): f is string => typeof f === 'string'));
    }
    setPersistReady(true);
  }, [storageKey]);

  // Prune fields the registry no longer offers (renamed / removed columns), once the list is known.
  useEffect(() => {
    if (!isSuccess || !items.length) return;
    const allowed = new Set(items.map((i) => i.field));
    setSelected((prev) => (prev.every((f) => allowed.has(f)) ? prev : prev.filter((f) => allowed.has(f))));
  }, [isSuccess, items]);

  useEffect(() => {
    if (!persistReady) return;
    writeStored(storageKey, selected);
  }, [selected, persistReady, storageKey]);

  const labelByField = useMemo(() => new Map(items.map((i) => [i.field, i.label])), [items]);
  const visibleFields = useMemo(() => selected.filter((f) => labelByField.has(f)), [selected, labelByField]);

  const optionalColDefs = useMemo<ColDef<T>[]>(
    () =>
      visibleFields.map((f) => {
        const fmt = formatters?.[f];
        return {
          colId: `opt:${f}`,
          field: f as ColDef<T>['field'],
          headerName: labelByField.get(f) ?? f,
          minWidth: 130,
          valueFormatter: (p: ValueFormatterParams<T>) => (fmt ? fmt(p.value) : fmtCellForKey(f, p.value)),
          ...colDefFor?.(f),
        };
      }),
    [visibleFields, labelByField, formatters, colDefFor]
  );

  const onToggle = useCallback((field: string, visible: boolean) => {
    setSelected((prev) => {
      const s = new Set(prev);
      if (visible) s.add(field);
      else s.delete(field);
      return [...s];
    });
  }, []);
  const onReset = useCallback(() => setSelected([]), []);
  const openPicker = useCallback(() => setOpen(true), []);
  const onClose = useCallback(() => setOpen(false), []);

  const pickerProps: FactColumnPickerProps = {
    open,
    onClose,
    gridId,
    items,
    selected,
    onToggle,
    onReset,
    gridReady: !isLoading,
    loading: isLoading,
  };

  return { optionalColDefs, optionalFields: visibleFields, pickerProps, openPicker, loading: isLoading };
}
