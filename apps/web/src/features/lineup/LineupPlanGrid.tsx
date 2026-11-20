'use client';

import { Alert, Box, Button, Stack, Typography } from '@mui/material';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import type { ColDef, GridOptions } from 'ag-grid-community';
import { useMemo, useState } from 'react';

import { EnterpriseDataGrid } from '@/components/EnterpriseDataGrid';
import {
  approvalBadgeLabel,
  formatUnits,
  isPendingApproval,
  type LineupPlanRow,
} from '@/features/lineup/lineupTypes';
import { useLineIdentifierPreference } from '@/features/tenant/useLineIdentifierPreference';
import { StatusChip } from '@/features/workbench-ui/controls';
import { apiPatch, safeDisplayError } from '@/lib/api';

function businessUnitLabel(row: LineupPlanRow): string {
  const productLine = row.product_line?.trim();
  if (productLine) return productLine;
  return `Not set: ${row.business_unit_reason || 'Product Master product line is unavailable'}`;
}

function approvalTone(status: string): 'success' | 'warning' | 'danger' | 'neutral' {
  if (status === 'approved') return 'success';
  if (isPendingApproval(status)) return 'warning';
  if (status === 'rejected') return 'danger';
  return 'neutral';
}

type Props = {
  rows: LineupPlanRow[];
  pendingOnly: boolean;
};

export function LineupPlanGrid({ rows, pendingOnly }: Props) {
  const qc = useQueryClient();
  const lineId = useLineIdentifierPreference();
  const [validationMessage, setValidationMessage] = useState<string | null>(null);

  const filtered = useMemo(
    () => pendingOnly ? rows.filter((row) => isPendingApproval(row.approval_status)) : rows,
    [pendingOnly, rows],
  );

  const patch = useMutation({
    mutationFn: ({
      id,
      body,
    }: {
      id: number;
      body: { approval_status: string } | { planned_volume_units: number };
    }) => apiPatch(`/api/v1/lineup/items/${id}`, body),
    onSuccess: () => void qc.invalidateQueries({ queryKey: ['lineup-items'] }),
  });

  const columns: ColDef<LineupPlanRow>[] = [
    {
      colId: 'customer_name',
      field: 'customer_name',
      headerName: 'Customer',
      minWidth: 160,
      valueGetter: (p) => p.data?.customer_name?.trim() || 'Customer name not set',
    },
    {
      colId: 'customer_code',
      field: 'customer_code',
      headerName: 'Customer code',
      minWidth: 130,
    },
    ...lineId.columns<LineupPlanRow>(
      { sku: 'sku', salesModel: 'sales_model_name' },
      { minWidth: 140 },
    ),
    {
      colId: 'period',
      field: 'period_label',
      headerName: 'Period',
      minWidth: 110,
      valueGetter: (p) => p.data?.period_label || p.data?.period_start,
    },
    {
      colId: 'planned_volume_units',
      field: 'planned_volume_units',
      headerName: 'Planned',
      minWidth: 120,
      type: 'numericColumn',
      editable: (p) => !patch.isPending && isPendingApproval(p.data?.approval_status ?? ''),
      valueFormatter: (p) => formatUnits(Number(p.value ?? 0)),
    },
    {
      colId: 'product_line',
      field: 'product_line',
      headerName: 'BU',
      minWidth: 240,
      valueGetter: (p) => p.data ? businessUnitLabel(p.data) : '',
    },
    {
      colId: 'approval_status',
      field: 'approval_status',
      headerName: 'Approval',
      minWidth: 130,
      cellRenderer: ({ data }: { data?: LineupPlanRow }) => data ? (
        <StatusChip
          label={approvalBadgeLabel(data.approval_status)}
          tone={approvalTone(data.approval_status)}
        />
      ) : null,
    },
    {
      colId: 'actions',
      headerName: 'Actions',
      minWidth: 190,
      sortable: false,
      filter: false,
      cellRenderer: ({ data }: { data?: LineupPlanRow }) => {
        if (!data || !isPendingApproval(data.approval_status)) return null;
        return (
          <Stack direction="row" spacing={0.75}>
            <Button
              size="small"
              color="success"
              disabled={patch.isPending}
              data-testid={`lineup-approve-${data.id}`}
              onClick={() => patch.mutate({ id: data.id, body: { approval_status: 'approved' } })}
            >
              Approve
            </Button>
            <Button
              size="small"
              color="error"
              disabled={patch.isPending}
              data-testid={`lineup-reject-${data.id}`}
              onClick={() => patch.mutate({ id: data.id, body: { approval_status: 'rejected' } })}
            >
              Reject
            </Button>
          </Stack>
        );
      },
    },
  ];

  const options: GridOptions<LineupPlanRow> = {
    getRowId: (p) => String(p.data.id),
    singleClickEdit: true,
    // Keep query data unchanged until the existing API has accepted the edit.
    readOnlyEdit: true,
    onCellEditRequest: (event) => {
      if (
        !event.data ||
        event.colDef.field !== 'planned_volume_units' ||
        !isPendingApproval(event.data.approval_status) ||
        event.oldValue === event.newValue
      ) return;

      const raw = String(event.newValue ?? '').trim();
      const value = Number(raw);
      if (!raw || !Number.isFinite(value) || value < 0) {
        setValidationMessage('Planned units must be a number greater than or equal to zero.');
        return;
      }
      setValidationMessage(null);
      patch.mutate({ id: event.data.id, body: { planned_volume_units: value } });
    },
  };

  return (
    <Box data-testid="lineup-plan-grid" sx={{ minWidth: 0 }}>
      {pendingOnly ? (
        <Typography data-testid="lineup-pending-directive" variant="body2" sx={{ px: 2.75, pb: 1 }}>
          {filtered.length} pending line{filtered.length === 1 ? '' : 's'} in this line-up.
        </Typography>
      ) : null}
      {validationMessage ? <Alert severity="warning">{validationMessage}</Alert> : null}
      {patch.isError ? <Alert severity="error">{safeDisplayError(patch.error)}</Alert> : null}
      <Box sx={{ px: 2.75 }}>
        <EnterpriseDataGrid rowData={filtered} columnDefs={columns} gridOptions={options} />
      </Box>
      <Typography
        data-testid="lineup-grid-footer"
        variant="body2"
        color="text.secondary"
        sx={{ px: 2.75, py: 1 }}
      >
        {filtered.length} of {rows.length} lines ·{' '}
        {rows.filter((row) => isPendingApproval(row.approval_status)).length} pending approval
      </Typography>
    </Box>
  );
}
