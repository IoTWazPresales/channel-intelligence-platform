'use client';

import { Alert, Box, Button, Stack, Typography } from '@mui/material';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import type { ColDef, GridOptions } from 'ag-grid-community';
import Link from 'next/link';
import { useMemo, useState } from 'react';

import { EnterpriseDataGrid } from '@/components/EnterpriseDataGrid';
import { LineupPlanGrid } from '@/features/lineup/LineupPlanGrid';
import { formatUnits, isPendingApproval, type LineupPlanRow } from '@/features/lineup/lineupTypes';
import {
  filterLineupRowsByExactProductId,
  groupLineupRows,
  workbenchSliceHref,
  type LineupGroup,
  type LineupSlice,
} from '@/features/lineup/lineupViews';
import { apiPost, safeDisplayError } from '@/lib/api';

type Props = {
  rows: LineupPlanRow[];
  slice: LineupSlice | null;
  pendingOnly?: boolean;
  productId?: number | null;
  onOpen?: (group: LineupGroup) => void;
};

type GroupGridRow = {
  key: string;
  group: LineupGroup;
  /** Present only on the full-width expansion row, inside the same grid. */
  detailRows?: LineupPlanRow[];
};

/** Existing customer/period grouping and approval flow, hosted by the shared grid. */
export function LineupGroupsPanel({
  rows,
  slice,
  pendingOnly = false,
  productId = null,
  onOpen,
}: Props) {
  const qc = useQueryClient();
  const [openedKey, setOpenedKey] = useState<string | null>(
    slice ? `${slice.customerId}|${slice.periodStart}` : null,
  );

  const decide = useMutation({
    mutationFn: (v: { group: LineupGroup; status: 'approved' | 'rejected' }) =>
      apiPost('/api/v1/lineup/items/group-approval', {
        customer_id: v.group.customerId,
        period_start: v.group.periodStart,
        approval_status: v.status,
        only_pending: true,
      }),
    onSuccess: () => void qc.invalidateQueries({ queryKey: ['lineup-items'] }),
  });

  const gridRows = useMemo(() => {
    const members = new Map<string, LineupPlanRow[]>();
    for (const row of rows) {
      if (row.customer_id == null) continue;
      const key = `${row.customer_id}|${row.period_start}`;
      const bucket = members.get(key);
      if (bucket) bucket.push(row);
      else members.set(key, [row]);
    }

    const result: GroupGridRow[] = [];
    for (const group of groupLineupRows(rows)) {
      const allLines = members.get(group.key) ?? [];
      const detailRows = productId == null
        ? allLines
        : filterLineupRowsByExactProductId(allLines, productId);
      const hasVisibleLines = pendingOnly
        ? detailRows.some((row) => isPendingApproval(row.approval_status))
        : detailRows.length > 0;
      if (!hasVisibleLines) continue;

      result.push({ key: group.key, group });
      if (openedKey === group.key) {
        result.push({ key: `detail|${group.key}`, group, detailRows });
      }
    }
    return result;
  }, [rows, openedKey, pendingOnly, productId]);

  const toggleGroup = (group: LineupGroup) => {
    if (openedKey === group.key) {
      setOpenedKey(null);
    } else {
      setOpenedKey(group.key);
      onOpen?.(group);
    }
  };

  const columns: ColDef<GroupGridRow>[] = [
    {
      colId: 'customer',
      headerName: 'Customer',
      minWidth: 180,
      flex: 1,
      valueGetter: (p) => p.data?.group.customerName,
    },
    {
      colId: 'period',
      headerName: 'Period',
      minWidth: 110,
      valueGetter: (p) => p.data?.group.periodLabel,
    },
    ...([
      ['lines', 'Lines'],
      ['plannedUnits', 'Units'],
      ['pending', 'Pending'],
      ['approved', 'Approved'],
      ['rejected', 'Rejected'],
    ] as const).map(([field, headerName]): ColDef<GroupGridRow> => ({
      colId: field,
      headerName,
      minWidth: 100,
      type: 'numericColumn',
      valueGetter: (p) => p.data?.group[field],
      valueFormatter: (p) => formatUnits(Number(p.value ?? 0)),
    })),
    {
      colId: 'actions',
      headerName: 'Actions',
      minWidth: 260,
      sortable: false,
      filter: false,
      cellRenderer: ({ data }: { data?: GroupGridRow }) => {
        if (!data || data.detailRows) return null;
        const group = data.group;
        const active = openedKey === group.key;
        return (
          <Stack
            direction="row"
            spacing={0.5}
            onClick={(event) => event.stopPropagation()}
            onKeyDown={(event) => event.stopPropagation()}
          >
            <Button
              size="small"
              data-testid={`lineup-group-open-${group.key}`}
              aria-expanded={active}
              onClick={() => toggleGroup(group)}
            >
              {active ? 'Close' : 'Open'}
            </Button>
            <Button
              size="small"
              color="success"
              disabled={decide.isPending || group.pending === 0}
              title="Approve all pending lines for this customer and period"
              data-testid={`lineup-group-approve-${group.key}`}
              onClick={() => decide.mutate({ group, status: 'approved' })}
            >
              Approve
            </Button>
            <Button
              size="small"
              color="error"
              disabled={decide.isPending || group.pending === 0}
              title="Reject all pending lines for this customer and period"
              data-testid={`lineup-group-reject-${group.key}`}
              onClick={() => decide.mutate({ group, status: 'rejected' })}
            >
              Reject
            </Button>
          </Stack>
        );
      },
    },
  ];

  const options: GridOptions<GroupGridRow> = {
    getRowId: (p) => p.data.key,
    onRowClicked: (event) => {
      if (event.data && !event.data.detailRows) toggleGroup(event.data.group);
    },
    isFullWidthRow: (p) => p.rowNode.data?.detailRows != null,
    getRowHeight: (p) => p.data?.detailRows != null ? 610 : undefined,
    fullWidthCellRenderer: ({ data }: { data?: GroupGridRow }) => {
      if (!data?.detailRows) return null;
      const group = data.group;
      return (
        <Box
          data-testid={`lineup-group-detail-${group.key}`}
          sx={{ height: '100%', overflow: 'auto', bgcolor: 'background.paper', py: 1 }}
        >
          <Stack direction="row" alignItems="center" spacing={1} sx={{ px: 2.75, pb: 1 }}>
            <Typography variant="subtitle2" sx={{ flex: 1 }}>
              {group.customerName} · {group.periodLabel}
            </Typography>
            <Button
              size="small"
              component={Link}
              href={workbenchSliceHref({
                customerId: group.customerId,
                periodStart: group.periodStart,
              })}
              data-testid={`lineup-group-workbench-${group.key}`}
            >
              Open in workbench
            </Button>
            <Button size="small" onClick={() => setOpenedKey(null)}>
              Close lines
            </Button>
          </Stack>
          <LineupPlanGrid rows={data.detailRows} pendingOnly={pendingOnly} />
        </Box>
      );
    },
  };

  const visibleGroups = gridRows.filter((row) => row.detailRows == null).length;

  return (
    <Box data-testid="lineup-groups" sx={{ minWidth: 0 }}>
      <Typography variant="subtitle2" sx={{ px: 1, pb: 1 }}>
        Line-ups by customer and period
      </Typography>
      {decide.isError ? <Alert severity="error">{safeDisplayError(decide.error)}</Alert> : null}
      <Typography variant="body2" color="text.secondary" sx={{ px: 1, pb: 1 }}>
        Approve and Reject apply to all pending lines in the customer&apos;s period.
        {productId != null
          ? ' Line-up totals include all products; the product filter limits matching line-ups and the lines shown when opened.'
          : ''}
      </Typography>
      <EnterpriseDataGrid
        rowData={gridRows}
        columnDefs={columns}
        height={640}
        gridOptions={options}
      />
      <Typography variant="body2" color="text.secondary" sx={{ px: 1, py: 1 }}>
        {visibleGroups} line-up{visibleGroups === 1 ? '' : 's'}
        {visibleGroups === 0 ? ' match the current filters.' : ' · Select a row or Open to view its lines.'}
      </Typography>
    </Box>
  );
}
