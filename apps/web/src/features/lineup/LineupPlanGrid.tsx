'use client';

import { Box, Button, Stack, Typography } from '@mui/material';
import { alpha, useTheme } from '@mui/material/styles';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import type { ColDef, GridOptions } from 'ag-grid-community';
import { useCallback, useMemo, useState } from 'react';

import { EnterpriseDataGrid } from '@/components/EnterpriseDataGrid';
import {
  approvalBadgeLabel,
  formatUnits,
  isPendingApproval,
  type LineupPlanRow,
} from '@/features/lineup/lineupTypes';
import { apiPatch } from '@/lib/api';

function buFromRow(row: LineupPlanRow): string {
  const sku = row.sku ?? '';
  const prefix = sku.split('-')[0];
  if (prefix && prefix.length <= 4) return prefix;
  return row.channel_code ?? '—';
}

function ApprovalBadge({ status }: { status: string }) {
  const theme = useTheme();
  const isOk = status === 'approved';
  const isPending = isPendingApproval(status);
  const isRejected = status === 'rejected';
  const tone = isOk
    ? theme.palette.success.main
    : isPending
      ? theme.palette.warning.main
      : isRejected
        ? theme.palette.error.main
        : theme.palette.text.secondary;
  return (
    <Box
      component="span"
      sx={{
        display: 'inline-block',
        fontFamily: '"IBM Plex Mono", monospace',
        fontSize: '9.5px',
        px: 0.75,
        py: 0.25,
        borderRadius: '3px',
        ml: 0.75,
        color: tone,
        border: `1px solid ${alpha(tone, 0.4)}`,
        bgcolor: isOk || isPending || isRejected ? alpha(tone, 0.14) : 'transparent',
      }}
    >
      {approvalBadgeLabel(status)}
    </Box>
  );
}

type Props = {
  rows: LineupPlanRow[];
  pendingOnly: boolean;
};

export function LineupPlanGrid({ rows, pendingOnly }: Props) {
  const theme = useTheme();
  const qc = useQueryClient();
  const [patchMsg, setPatchMsg] = useState<string | null>(null);

  const filtered = useMemo(
    () => (pendingOnly ? rows.filter((r) => isPendingApproval(r.approval_status)) : rows),
    [pendingOnly, rows],
  );

  const patchApproval = useMutation({
    mutationFn: ({ id, status }: { id: number; status: string }) =>
      apiPatch(`/api/v1/lineup/items/${id}`, { approval_status: status }),
    onSuccess: () => void qc.invalidateQueries({ queryKey: ['lineup-items'] }),
  });

  const patchPlanned = useMutation({
    mutationFn: ({ id, planned_volume_units }: { id: number; planned_volume_units: number }) =>
      apiPatch(`/api/v1/lineup/items/${id}`, { planned_volume_units }),
    onSuccess: () => void qc.invalidateQueries({ queryKey: ['lineup-items'] }),
  });

  const onApprove = useCallback((id: number) => void patchApproval.mutate({ id, status: 'approved' }), [patchApproval]);
  const onReject = useCallback((id: number) => void patchApproval.mutate({ id, status: 'rejected' }), [patchApproval]);

  const colDefs: ColDef<LineupPlanRow>[] = useMemo(
    () => [
      {
        field: 'customer_name',
        headerName: 'Customer',
        minWidth: 140,
        valueGetter: (p) => p.data?.customer_name || p.data?.customer_code || '—',
      },
      { field: 'sku', headerName: 'SKU', minWidth: 120, cellClass: 'lineup-sku-cell' },
      { field: 'period_label', headerName: 'Period', minWidth: 100 },
      {
        field: 'planned_volume_units',
        headerName: 'Planned',
        minWidth: 110,
        type: 'numericColumn',
        editable: (p) => isPendingApproval(p.data?.approval_status ?? ''),
        cellClass: (p) => (isPendingApproval(p.data?.approval_status ?? '') ? 'lineup-planned-edit' : ''),
        valueFormatter: (p) => formatUnits(Number(p.value ?? 0)),
      },
      {
        headerName: 'BU',
        minWidth: 70,
        valueGetter: (p) => (p.data ? buFromRow(p.data) : '—'),
        cellClass: 'lineup-bu-cell',
      },
      {
        field: 'approval_status',
        headerName: 'Approval',
        minWidth: 130,
        cellRenderer: (p: { data?: LineupPlanRow }) =>
          p.data ? <ApprovalBadge status={p.data.approval_status} /> : null,
      },
      {
        headerName: '',
        minWidth: 150,
        cellRenderer: (p: { data?: LineupPlanRow }) => {
          const row = p.data;
          if (!row || !isPendingApproval(row.approval_status)) return null;
          return (
            <Stack direction="row" spacing={0.75} justifyContent="flex-end">
              <Button
                size="small"
                data-testid={`lineup-approve-${row.id}`}
                onClick={() => onApprove(row.id)}
                sx={{
                  fontSize: '11px',
                  py: 0.5,
                  px: 1,
                  minWidth: 0,
                  color: 'success.main',
                  borderColor: alpha(theme.palette.success.main, 0.4),
                }}
                variant="outlined"
              >
                Approve
              </Button>
              <Button
                size="small"
                data-testid={`lineup-reject-${row.id}`}
                onClick={() => onReject(row.id)}
                sx={{
                  fontSize: '11px',
                  py: 0.5,
                  px: 1,
                  minWidth: 0,
                  color: 'error.main',
                  borderColor: alpha(theme.palette.error.main, 0.4),
                }}
                variant="outlined"
              >
                Reject
              </Button>
            </Stack>
          );
        },
      },
    ],
    [onApprove, onReject, theme],
  );

  const gridOptions: GridOptions<LineupPlanRow> = useMemo(
    () => ({
      singleClickEdit: true,
      onCellValueChanged: async (e) => {
        const id = e.data?.id;
        if (id == null || e.colDef.field !== 'planned_volume_units' || e.oldValue === e.newValue) return;
        const val = Number(e.newValue);
        if (!Number.isFinite(val) || val < 0) return;
        try {
          await patchPlanned.mutateAsync({ id, planned_volume_units: val });
        } catch (err) {
          setPatchMsg(err instanceof Error ? err.message : String(err));
        }
      },
    }),
    [patchPlanned],
  );

  return (
    <Box data-testid="lineup-plan-grid" sx={{ flex: 1, minHeight: 320 }}>
      {pendingOnly ? (
        <Typography data-testid="lineup-pending-directive" sx={{ fontSize: '12px', color: alpha(theme.palette.text.primary, 0.75), px: 2.75, py: 1 }}>
          {filtered.length} lineup item{filtered.length === 1 ? '' : 's'} await approval — Approve or Reject each row before Stock can trust Execution vs plan.
        </Typography>
      ) : null}
      {patchMsg ? (
        <Typography color="warning.main" sx={{ px: 2.75, py: 0.5, fontSize: '12px' }}>
          {patchMsg}
        </Typography>
      ) : null}
      <Box
        sx={{
          px: 2.75,
          '& .lineup-sku-cell': { fontFamily: '"IBM Plex Mono", monospace', fontSize: '11.5px' },
          '& .lineup-bu-cell': { fontFamily: '"IBM Plex Mono", monospace', fontSize: '11px' },
          '& .lineup-planned-edit': {
            cursor: 'text',
            '& .ag-cell-value': { borderBottom: `1px dashed ${alpha(theme.palette.primary.main, 0.45)}` },
          },
        }}
      >
        <EnterpriseDataGrid rowData={filtered} columnDefs={colDefs} gridOptions={gridOptions} />
      </Box>
      <Box
        data-testid="lineup-grid-footer"
        sx={{
          display: 'flex',
          gap: 2.25,
          px: 2.75,
          py: 1,
          borderTop: `1px solid ${theme.palette.divider}`,
          fontFamily: '"IBM Plex Mono", monospace',
          fontSize: '11px',
          color: alpha(theme.palette.text.primary, 0.45),
        }}
      >
        <span>
          1–{filtered.length} of {rows.length}
        </span>
        <span>
          {rows.filter((r) => isPendingApproval(r.approval_status)).length} pending approval
        </span>
        {pendingOnly ? <span style={{ marginLeft: 'auto' }}>Clear filter to return to full lineup</span> : <span style={{ marginLeft: 'auto' }}>Sorted by customer, period</span>}
      </Box>
    </Box>
  );
}
