'use client';

import { Alert, Box, Paper, Stack, Typography } from '@mui/material';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import type { ColDef, GridOptions, GridReadyEvent } from 'ag-grid-community';
import { useCallback, useEffect, useMemo, useState } from 'react';

import { BulkSelectionToolbar, type BulkTableSelectionMode } from '@/components/bulkTable/BulkSelectionToolbar';
import {
  MasterBulkDeleteImpactDialog,
  type MasterBulkDeletePreview,
} from '@/components/bulkTable/MasterBulkDeleteImpactDialog';
import { EnterpriseDataGrid } from '@/components/EnterpriseDataGrid';
import { ModuleDataSection } from '@/components/ModuleDataSection';
import { ModuleGridToolbar } from '@/components/ModuleGridToolbar';
import { gridDeleteColumn } from '@/components/gridDeleteColumn';
import { apiDelete, apiGet, apiPost, HttpConflictError, safeDisplayError } from '@/lib/api';
import { toQueryError } from '@/lib/queryError';

export type CatalogDimensionRow = { id: number; code: string; name: string };

export type CatalogDimensionGridConfig = {
  dimensionTitle: string;
  tableName: string;
  listPath: string;
  deletePath: (id: number) => string;
  bulkPreviewPath: string;
  bulkConfirmPath: string;
  queryKey: string;
  entityLabel: string;
  deleteConfirmMessage: string;
};

export function CatalogDimensionGridPanel({ config }: { config: CatalogDimensionGridConfig }) {
  const qc = useQueryClient();
  const [gridApi, setGridApi] = useState<{ getSelectedRows: () => CatalogDimensionRow[]; deselectAll: () => void; forEachNodeAfterFilterAndSort: (cb: (n: { data?: CatalogDimensionRow; setSelected: (v: boolean) => void }) => void) => void; getDisplayedRowCount: () => number } | null>(null);
  const [bulkSelectionMode, setBulkSelectionMode] = useState<BulkTableSelectionMode>('normal');
  const [bulkSelectedCount, setBulkSelectedCount] = useState(0);
  const [visibleRowCount, setVisibleRowCount] = useState(0);
  const [bulkDeleteOpen, setBulkDeleteOpen] = useState(false);
  const [bulkDeletePreview, setBulkDeletePreview] = useState<MasterBulkDeletePreview | null>(null);
  const [bulkDeleteBusy, setBulkDeleteBusy] = useState(false);
  const [bulkDeleteAck, setBulkDeleteAck] = useState(false);

  const { data, isLoading, isError, error, refetch } = useQuery({
    queryKey: [config.queryKey],
    queryFn: ({ signal }) => apiGet<CatalogDimensionRow[]>(config.listPath, { signal }),
  });

  const delRow = useMutation({
    mutationFn: (id: number) => apiDelete(config.deletePath(id)),
    onSuccess: () => qc.invalidateQueries({ queryKey: [config.queryKey] }),
  });

  const rows = data ?? [];

  useEffect(() => {
    if (bulkSelectionMode !== 'selecting') {
      gridApi?.deselectAll();
      setBulkSelectedCount(0);
    }
  }, [bulkSelectionMode, gridApi]);

  useEffect(() => {
    setVisibleRowCount(rows.length);
  }, [rows.length]);

  const openBulkDeletePreview = useCallback(async () => {
    if (!gridApi) return;
    const ids = gridApi.getSelectedRows().map((r) => r.id);
    if (!ids.length) return;
    setBulkDeleteBusy(true);
    setBulkDeleteAck(false);
    try {
      const preview = await apiPost<MasterBulkDeletePreview>(config.bulkPreviewPath, { entity_ids: ids });
      setBulkDeletePreview(preview);
      setBulkDeleteOpen(true);
    } catch (e) {
      alert(safeDisplayError(e));
    } finally {
      setBulkDeleteBusy(false);
    }
  }, [config.bulkPreviewPath, gridApi]);

  const closeBulkDeleteDialog = useCallback(() => {
    if (bulkDeleteBusy) return;
    setBulkDeleteOpen(false);
    setBulkDeletePreview(null);
  }, [bulkDeleteBusy]);

  const confirmBulkDelete = useCallback(async () => {
    if (!bulkDeletePreview) return;
    setBulkDeleteBusy(true);
    try {
      await apiPost(config.bulkConfirmPath, { entity_ids: bulkDeletePreview.entity_ids });
      setBulkDeleteOpen(false);
      setBulkDeletePreview(null);
      setBulkSelectionMode('normal');
      delRow.reset();
      await qc.invalidateQueries({ queryKey: [config.queryKey] });
    } catch (e) {
      alert(safeDisplayError(e));
    } finally {
      setBulkDeleteBusy(false);
    }
  }, [bulkDeletePreview, config.bulkConfirmPath, delRow, qc, config.queryKey]);

  const colDefs: ColDef<CatalogDimensionRow>[] = useMemo(
    () => [
      { field: 'code', headerName: 'Code', pinned: 'left', minWidth: 120, editable: false },
      { field: 'name', headerName: 'Name', flex: 1, minWidth: 200, editable: false },
      gridDeleteColumn<CatalogDimensionRow>((id) => delRow.mutate(id), {
        busy: delRow.isPending,
        confirmMessage: config.deleteConfirmMessage,
      }),
    ],
    [config.deleteConfirmMessage, delRow]
  );

  const gridOptions: GridOptions<CatalogDimensionRow> = useMemo(() => {
    const base: GridOptions<CatalogDimensionRow> = {
      onGridReady: (e: GridReadyEvent<CatalogDimensionRow>) => {
        setGridApi(e.api);
        setVisibleRowCount(e.api.getDisplayedRowCount());
      },
      onFilterChanged: (e) => {
        if (bulkSelectionMode === 'selecting') setVisibleRowCount(e.api.getDisplayedRowCount());
      },
      onSortChanged: (e) => {
        if (bulkSelectionMode === 'selecting') setVisibleRowCount(e.api.getDisplayedRowCount());
      },
    };
    if (bulkSelectionMode !== 'selecting') return base;
    return {
      ...base,
      rowSelection: {
        mode: 'multiRow',
        checkboxes: true,
        headerCheckbox: true,
        enableClickSelection: false,
      },
      onSelectionChanged: (e) => {
        setBulkSelectedCount(e.api.getSelectedRows().length);
      },
    };
  }, [bulkSelectionMode]);

  return (
    <>
      {delRow.isError ? (
        <Alert severity="warning" sx={{ mb: 2 }} onClose={() => delRow.reset()}>
          {HttpConflictError.is(delRow.error) ? (
            <Stack spacing={1}>
              <Typography variant="body2">{delRow.error.message}</Typography>
              {delRow.error.references.length > 0 ? (
                <Box component="ul" sx={{ m: 0, pl: 2 }}>
                  {delRow.error.references.map((r) => (
                    <Typography key={`${r.label}-${r.count}`} component="li" variant="body2">
                      {r.label} ({r.count})
                    </Typography>
                  ))}
                </Box>
              ) : null}
            </Stack>
          ) : (
            <Typography variant="body2">{(delRow.error as Error).message}</Typography>
          )}
        </Alert>
      ) : null}
      <Stack direction="row" spacing={1} sx={{ mb: 2 }} flexWrap="wrap" useFlexGap alignItems="center">
        <ModuleGridToolbar
          onRefresh={() => void refetch()}
          sx={{ mb: 0 }}
          busy={delRow.isPending || bulkDeleteBusy}
        />
        <BulkSelectionToolbar
          mode={bulkSelectionMode}
          selectedCount={bulkSelectedCount}
          visibleRowCount={visibleRowCount}
          onEnterSelectionMode={() => setBulkSelectionMode('selecting')}
          onExitSelectionMode={() => setBulkSelectionMode('normal')}
          onSelectAllVisible={() => {
            if (!gridApi) return;
            gridApi.forEachNodeAfterFilterAndSort((node) => {
              if (node.data) node.setSelected(true);
            });
          }}
          onDeselectAll={() => gridApi?.deselectAll()}
          onPreviewDangerAction={() => void openBulkDeletePreview()}
          previewDangerDisabled={bulkDeleteBusy}
          busy={bulkDeleteBusy}
        />
      </Stack>
      <Paper sx={{ p: 2 }}>
        <ModuleDataSection
          intro={
            <>
              Master list in <strong>{config.tableName}</strong>. Deleting a row blocked by downstream references
              shows which areas still point at this {config.dimensionTitle.toLowerCase()}.
            </>
          }
          isLoading={isLoading}
          isError={isError}
          error={toQueryError(error)}
          onRetry={() => void refetch()}
          isEmpty={rows.length === 0}
          empty={{
            title: `No ${config.dimensionTitle.toLowerCase()}s yet`,
            description: `${config.dimensionTitle}s are created through imports and steward workflows.`,
          }}
        >
          <EnterpriseDataGrid
            key={bulkSelectionMode === 'selecting' ? `${config.queryKey}-bulk` : `${config.queryKey}-normal`}
            rowData={rows}
            columnDefs={colDefs}
            gridOptions={gridOptions}
            height={480}
          />
        </ModuleDataSection>
      </Paper>
      <MasterBulkDeleteImpactDialog
        open={bulkDeleteOpen}
        busy={bulkDeleteBusy}
        preview={bulkDeletePreview}
        entityLabel={config.entityLabel}
        impactAcknowledged={bulkDeleteAck}
        onImpactAcknowledgedChange={setBulkDeleteAck}
        onClose={closeBulkDeleteDialog}
        onConfirm={() => void confirmBulkDelete()}
      />
    </>
  );
}
