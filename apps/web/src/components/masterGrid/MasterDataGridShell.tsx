'use client';

import {
  Box,
  Button,
  Drawer,
  FormControl,
  InputLabel,
  MenuItem,
  Paper,
  Select,
  Stack,
  Typography,
} from '@mui/material';
import type {
  CellValueChangedEvent,
  ColDef,
  ColumnMovedEvent,
  ColumnPinnedEvent,
  ColumnResizedEvent,
  ColumnVisibleEvent,
  GridApi,
  GridOptions,
  GridReadyEvent,
} from 'ag-grid-community';
import { usePathname, useRouter, useSearchParams } from 'next/navigation';
import { useCallback, useEffect, useMemo, useState, type ReactNode } from 'react';

import { BulkSelectionToolbar, type BulkTableSelectionMode } from '@/components/bulkTable/BulkSelectionToolbar';
import { EnterpriseDataGrid } from '@/components/EnterpriseDataGrid';
import { ModuleDataSection } from '@/components/ModuleDataSection';
import { ModuleGridToolbar } from '@/components/ModuleGridToolbar';
import {
  MasterColumnPickerDialog,
  type MasterColumnPickerGroup,
} from '@/components/masterGrid/MasterColumnPickerDialog';

export type MasterGridUrlState = {
  page: number;
  pageSize: number;
  q: string;
  sortBy: string;
  sortDir: 'asc' | 'desc';
};

export type MasterDataGridShellProps<TRow extends { id: number }> = {
  /** Stable id for testids / remount keys, e.g. "customers" | "products" | "distributors" */
  entityKey: string;

  rows: TRow[];
  columnDefs: ColDef<TRow>[];
  total: number;
  isLoading?: boolean;
  isError?: boolean;
  error?: Error | null;
  onRetry?: () => void;
  empty: {
    title: string;
    description: string;
    primary?: { label: string; href: string };
    secondary?: { label: string; href: string };
  };
  intro?: ReactNode;

  url: MasterGridUrlState;
  onUrlChange: (patch: Record<string, string | null>, resetPage?: boolean) => void;
  defaultPageSize: number;
  defaultSortBy: string;
  defaultSortDir: 'asc' | 'desc';
  pageSizeOptions?: number[];
  /** When true, empty search string seeds page/page_size/sort_* defaults (customers behaviour). */
  enableEmptyUrlSeed?: boolean;

  gridStateStorageKey: string;
  defaultInitiallyHiddenFields?: readonly string[];
  columnPickerTitle: string;
  columnPickerGroups: MasterColumnPickerGroup[];
  /** Optional extra groups (e.g. products discovered specs) — U-B2 */
  columnPickerExtraGroups?: MasterColumnPickerGroup[];
  columnLabelByField?: Record<string, string>;

  gridHeight?: number | string;
  gridOptions?: GridOptions<TRow>;
  onCellValueChanged?: (e: CellValueChangedEvent<TRow>) => void | Promise<void>;
  onGridApiChange?: (api: GridApi<TRow> | null) => void;

  bulkSelectionEnabled?: boolean;
  bulkSelectionMode: BulkTableSelectionMode;
  onBulkSelectionModeChange: (mode: BulkTableSelectionMode) => void;
  onPreviewBulkDelete: () => void;
  previewBulkDeleteDisabled?: boolean;
  bulkBusy?: boolean;
  bulkSelectingActions?: ReactNode;
  onBulkSelectedCountChange?: (count: number) => void;

  toolbarStart?: ReactNode;
  filterSlot?: ReactNode;
  toolbarEnd?: ReactNode;
  onRefresh?: () => void;
  refreshBusy?: boolean;

  drawer?: {
    open: boolean;
    onClose: () => void;
    width?: number;
    title?: string;
    children: ReactNode;
  };
};

export function MasterDataGridShell<TRow extends { id: number }>({
  entityKey,
  rows,
  columnDefs,
  total,
  isLoading,
  isError,
  error,
  onRetry,
  empty,
  intro,
  url,
  onUrlChange,
  defaultPageSize,
  defaultSortBy,
  defaultSortDir,
  pageSizeOptions = [25, 50, 100, 200],
  enableEmptyUrlSeed = true,
  gridStateStorageKey,
  defaultInitiallyHiddenFields = [],
  columnPickerTitle,
  columnPickerGroups,
  columnPickerExtraGroups,
  columnLabelByField,
  gridHeight = 520,
  gridOptions: pageGridOptions,
  onCellValueChanged,
  onGridApiChange,
  bulkSelectionEnabled = true,
  bulkSelectionMode,
  onBulkSelectionModeChange,
  onPreviewBulkDelete,
  previewBulkDeleteDisabled,
  bulkBusy,
  bulkSelectingActions,
  onBulkSelectedCountChange,
  toolbarStart,
  filterSlot,
  toolbarEnd,
  onRefresh,
  refreshBusy,
  drawer,
}: MasterDataGridShellProps<TRow>) {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();

  const [gridApi, setGridApi] = useState<GridApi<TRow> | null>(null);
  const [bulkSelectedCount, setBulkSelectedCount] = useState(0);
  const [visibleRowCount, setVisibleRowCount] = useState(0);
  const [columnsOpen, setColumnsOpen] = useState(false);
  const [columnSearch, setColumnSearch] = useState('');
  const [columnVisibility, setColumnVisibility] = useState<Record<string, boolean>>({});

  useEffect(() => {
    if (!enableEmptyUrlSeed) return;
    if (!searchParams.toString()) {
      const sp = new URLSearchParams();
      sp.set('page', '1');
      sp.set('page_size', String(defaultPageSize));
      sp.set('sort_by', defaultSortBy);
      sp.set('sort_dir', defaultSortDir);
      router.replace(`${pathname}?${sp.toString()}`);
    }
  }, [
    enableEmptyUrlSeed,
    pathname,
    router,
    searchParams,
    defaultPageSize,
    defaultSortBy,
    defaultSortDir,
  ]);

  const allColumnPickerGroups = useMemo(
    () => [...columnPickerGroups, ...(columnPickerExtraGroups ?? [])],
    [columnPickerGroups, columnPickerExtraGroups]
  );

  const persistGridState = useCallback(
    (api: GridApi<TRow>) => {
      try {
        const state = api.getColumnState();
        localStorage.setItem(gridStateStorageKey, JSON.stringify(state));
      } catch {
        // no-op
      }
    },
    [gridStateStorageKey]
  );

  const syncColumnVisibility = useCallback(
    (api: GridApi<TRow>) => {
      if (!api?.getColumns) return;
      try {
        const known = new Set(allColumnPickerGroups.flatMap((g) => g.fields));
        const visibility: Record<string, boolean> = {};
        for (const col of api.getColumns() ?? []) {
          const def = col?.getColDef?.();
          const field = def?.field as string | undefined;
          if (!field || !known.has(field)) continue;
          visibility[field] = Boolean(col.isVisible?.());
        }
        if (Object.keys(visibility).length) setColumnVisibility(visibility);
      } catch {
        // no-op
      }
    },
    [allColumnPickerGroups]
  );

  const setGridApiAndNotify = useCallback(
    (api: GridApi<TRow> | null) => {
      setGridApi(api);
      onGridApiChange?.(api);
    },
    [onGridApiChange]
  );

  const onGridReady = useCallback(
    (e: GridReadyEvent<TRow>) => {
      setGridApiAndNotify(e.api);
      try {
        const raw = localStorage.getItem(gridStateStorageKey);
        if (raw) {
          e.api.applyColumnState({ state: JSON.parse(raw), applyOrder: true });
        } else if (defaultInitiallyHiddenFields.length) {
          e.api.applyColumnState({
            state: defaultInitiallyHiddenFields.map((colId) => ({ colId, hide: true })),
            applyOrder: true,
          });
        }
      } catch {
        // no-op
      }
      syncColumnVisibility(e.api);
      setVisibleRowCount(
        typeof e.api.getDisplayedRowCount === 'function' ? e.api.getDisplayedRowCount() : 0
      );
    },
    [
      defaultInitiallyHiddenFields,
      gridStateStorageKey,
      setGridApiAndNotify,
      syncColumnVisibility,
    ]
  );

  const onColumnStateEvent = useCallback(
    (
      e:
        | ColumnMovedEvent<TRow>
        | ColumnVisibleEvent<TRow>
        | ColumnPinnedEvent<TRow>
        | ColumnResizedEvent<TRow>
    ) => {
      persistGridState(e.api);
      syncColumnVisibility(e.api);
    },
    [persistGridState, syncColumnVisibility]
  );

  const toggleColumnVisibility = useCallback(
    (columnId: string, visible: boolean) => {
      if (!gridApi?.setColumnsVisible) return;
      gridApi.setColumnsVisible([columnId], visible);
      persistGridState(gridApi);
      setColumnVisibility((prev) => ({ ...prev, [columnId]: visible }));
    },
    [gridApi, persistGridState]
  );

  useEffect(() => {
    if (bulkSelectionMode !== 'selecting') {
      gridApi?.deselectAll();
      setBulkSelectedCount(0);
      onBulkSelectedCountChange?.(0);
    }
  }, [bulkSelectionMode, gridApi, onBulkSelectedCountChange]);

  useEffect(() => {
    setVisibleRowCount(rows.length);
  }, [rows]);

  const updateSelectedCount = useCallback(
    (count: number) => {
      setBulkSelectedCount(count);
      onBulkSelectedCountChange?.(count);
    },
    [onBulkSelectedCountChange]
  );

  const mergedGridOptions: GridOptions<TRow> = useMemo(() => {
    const base: GridOptions<TRow> = {
      singleClickEdit: true,
      ...(pageGridOptions ?? {}),
      onCellValueChanged: (e) => {
        pageGridOptions?.onCellValueChanged?.(e);
        void onCellValueChanged?.(e);
      },
      onGridReady: (e) => {
        onGridReady(e);
        pageGridOptions?.onGridReady?.(e);
      },
      onColumnMoved: (e) => {
        onColumnStateEvent(e);
        pageGridOptions?.onColumnMoved?.(e);
      },
      onColumnVisible: (e) => {
        onColumnStateEvent(e);
        pageGridOptions?.onColumnVisible?.(e);
      },
      onColumnPinned: (e) => {
        onColumnStateEvent(e);
        pageGridOptions?.onColumnPinned?.(e);
      },
      onColumnResized: (e) => {
        onColumnStateEvent(e);
        pageGridOptions?.onColumnResized?.(e);
      },
      onFilterChanged: (e) => {
        if (bulkSelectionMode === 'selecting' && typeof e.api.getDisplayedRowCount === 'function') {
          setVisibleRowCount(e.api.getDisplayedRowCount());
        }
        pageGridOptions?.onFilterChanged?.(e);
      },
      onSortChanged: (e) => {
        if (bulkSelectionMode === 'selecting' && typeof e.api.getDisplayedRowCount === 'function') {
          setVisibleRowCount(e.api.getDisplayedRowCount());
        }
        pageGridOptions?.onSortChanged?.(e);
      },
    };
    if (!bulkSelectionEnabled || bulkSelectionMode !== 'selecting') return base;
    return {
      ...base,
      rowSelection: {
        mode: 'multiRow',
        checkboxes: true,
        headerCheckbox: true,
        enableClickSelection: false,
      },
      onSelectionChanged: (e) => {
        updateSelectedCount(e.api.getSelectedRows().length);
        pageGridOptions?.onSelectionChanged?.(e);
      },
    };
  }, [
    bulkSelectionEnabled,
    bulkSelectionMode,
    onCellValueChanged,
    onColumnStateEvent,
    onGridReady,
    pageGridOptions,
    updateSelectedCount,
  ]);

  const totalPages = Math.max(1, Math.ceil(total / url.pageSize));

  return (
    <>
      <Stack direction="row" spacing={1} sx={{ mb: 2 }} flexWrap="wrap" useFlexGap>
        {toolbarStart}
        <Button
          variant="outlined"
          disabled={!gridApi}
          onClick={() => {
            setColumnSearch('');
            setColumnsOpen(true);
            if (gridApi) syncColumnVisibility(gridApi);
          }}
          data-testid={`${entityKey}-columns-open`}
        >
          Columns
        </Button>
        <Button
          variant="outlined"
          onClick={() => {
            try {
              localStorage.removeItem(gridStateStorageKey);
              window.location.reload();
            } catch {
              // no-op
            }
          }}
          data-testid={`${entityKey}-columns-reset`}
        >
          Reset column layout
        </Button>
        {onRefresh ? (
          <ModuleGridToolbar onRefresh={onRefresh} sx={{ mb: 0 }} busy={refreshBusy || bulkBusy} />
        ) : null}
        {bulkSelectionEnabled ? (
          <BulkSelectionToolbar
            mode={bulkSelectionMode}
            selectedCount={bulkSelectedCount}
            visibleRowCount={visibleRowCount}
            onEnterSelectionMode={() => onBulkSelectionModeChange('selecting')}
            onExitSelectionMode={() => onBulkSelectionModeChange('normal')}
            onSelectAllVisible={() => {
              if (!gridApi) return;
              gridApi.forEachNodeAfterFilterAndSort((node) => {
                if (node.data) node.setSelected(true);
              });
            }}
            onDeselectAll={() => gridApi?.deselectAll()}
            onPreviewDangerAction={onPreviewBulkDelete}
            previewDangerDisabled={previewBulkDeleteDisabled}
            busy={bulkBusy}
          />
        ) : null}
        {bulkSelectionMode === 'selecting' ? bulkSelectingActions : null}
        {toolbarEnd}
      </Stack>

      {filterSlot ? (
        <Paper sx={{ p: 2, mb: 2 }} data-testid={`${entityKey}-filter-slot`}>
          {filterSlot}
        </Paper>
      ) : null}

      <Paper sx={{ p: 2 }}>
        <ModuleDataSection
          intro={intro}
          isLoading={Boolean(isLoading)}
          isError={Boolean(isError)}
          error={error ?? null}
          onRetry={onRetry}
          isEmpty={rows.length === 0}
          empty={empty}
        >
          <EnterpriseDataGrid
            key={bulkSelectionMode === 'selecting' ? `${entityKey}-bulk` : `${entityKey}-normal`}
            rowData={rows}
            columnDefs={columnDefs as ColDef[]}
            gridOptions={mergedGridOptions as GridOptions}
            height={gridHeight}
          />
          <Stack direction="row" spacing={1} sx={{ mt: 2 }} alignItems="center">
            <Button
              disabled={url.page <= 1}
              onClick={() => onUrlChange({ page: String(url.page - 1) })}
            >
              Prev
            </Button>
            <Typography variant="body2">
              Page {url.page} / {totalPages} ({total} rows)
            </Typography>
            <Button
              disabled={url.page >= totalPages}
              onClick={() => onUrlChange({ page: String(url.page + 1) })}
            >
              Next
            </Button>
            <FormControl size="small" sx={{ minWidth: 120 }}>
              <InputLabel>Page size</InputLabel>
              <Select
                label="Page size"
                value={String(url.pageSize)}
                onChange={(e) =>
                  onUrlChange({ page_size: String(e.target.value || defaultPageSize) }, true)
                }
              >
                {pageSizeOptions.map((n) => (
                  <MenuItem key={n} value={String(n)}>
                    {n}
                  </MenuItem>
                ))}
              </Select>
            </FormControl>
          </Stack>
        </ModuleDataSection>
      </Paper>

      <MasterColumnPickerDialog
        open={columnsOpen}
        onClose={() => setColumnsOpen(false)}
        title={columnPickerTitle}
        groups={allColumnPickerGroups}
        columnLabelByField={columnLabelByField}
        visibility={columnVisibility}
        onToggle={toggleColumnVisibility}
        gridReady={Boolean(gridApi)}
        search={columnSearch}
        onSearchChange={setColumnSearch}
      />

      {drawer ? (
        <Drawer
          anchor="right"
          open={drawer.open}
          onClose={drawer.onClose}
          sx={{
            '& .MuiDrawer-paper': {
              width: drawer.width ?? 520,
              top: { xs: 56, sm: 64 },
              height: { xs: 'calc(100% - 56px)', sm: 'calc(100% - 64px)' },
            },
          }}
        >
          <Box sx={{ p: 2, width: drawer.width ?? 520 }}>
            {drawer.title ? (
              <Typography variant="h6" sx={{ mb: 1 }}>
                {drawer.title}
              </Typography>
            ) : null}
            {drawer.children}
          </Box>
        </Drawer>
      ) : null}
    </>
  );
}
