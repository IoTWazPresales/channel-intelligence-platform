'use client';

import WarningAmberIcon from '@mui/icons-material/WarningAmber';
import {
  Alert,
  Box,
  Paper,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TablePagination,
  TableRow,
  Typography,
} from '@mui/material';
import { useQuery } from '@tanstack/react-query';
import { useEffect, useState } from 'react';

import { apiGet } from '@/lib/api';

import { depthAtLeast, type IntelDepth } from './intelDepth';

type InvRow = {
  distributor_id: number;
  distributor_name: string | null;
  product_id: number;
  sku: string | null;
  product_name: string | null;
  snapshot_date?: string | null;
  reported_soh: number;
  sell_out_since?: number;
  landed_since?: number;
  derived_stock?: number;
  calculated_soh: number | null;
  variance_units: number | null;
  variance_pct: number | null;
  reconciliation_status: string | null;
  velocity_52wk: number | null;
  weeks_of_cover: number | null;
  computed_through_date: string | null;
  reorder_signal: boolean;
};

const PAGE_SIZE_OPTIONS = [25, 50, 100] as const;
const DEFAULT_PAGE_SIZE = 50;

export function ChannelOpsInventoryTab({
  depth,
  distributorId,
}: {
  depth: IntelDepth;
  distributorId?: number | null;
}) {
  const [page, setPage] = useState(0);
  const [pageSize, setPageSize] = useState(DEFAULT_PAGE_SIZE);
  const distId = distributorId ?? null;

  useEffect(() => {
    setPage(0);
  }, [distId]);

  const { data, isLoading, isError, error } = useQuery({
    queryKey: ['channel-ops-inventory', distId, page, pageSize],
    queryFn: ({ signal }) =>
      apiGet<{
        items: InvRow[];
        total: number;
        page: number;
        page_size: number;
        truncated?: boolean;
        true_total?: number;
      }>(
        `/api/v1/channel-ops/inventory?distributor_id=${distId}&page=${page + 1}&page_size=${pageSize}`,
        { signal }
      ),
    enabled: distId != null,
  });

  if (distId == null) {
    return (
      <Alert severity="info" data-testid="inventory-distributor-required">
        Select a distributor above to load inventory. Inventory is computed per distributor from the latest DSI
        snapshot (derived stock) — there is no all-distributor inventory grid yet.
      </Alert>
    );
  }

  return (
    <Box>
      {isError && (
        <Alert severity="error" sx={{ mb: 2 }}>
          {(error as Error)?.message ?? 'Failed to load inventory.'}
        </Alert>
      )}
      {data?.truncated ? (
        <Alert severity="warning" sx={{ mb: 2 }}>
          Soft cap: paging the first {data.total.toLocaleString()} of{' '}
          {(data.true_total ?? data.total).toLocaleString()} products for this distributor.
        </Alert>
      ) : null}
      <Paper variant="outlined">
        <Box sx={{ p: 2 }}>
          {data != null && data.total > 0 ? (
            <TablePagination
              component="div"
              count={data.total}
              page={page}
              onPageChange={(_e, nextPage) => setPage(nextPage)}
              rowsPerPage={pageSize}
              onRowsPerPageChange={(e) => {
                setPageSize(Number(e.target.value));
                setPage(0);
              }}
              rowsPerPageOptions={[...PAGE_SIZE_OPTIONS]}
              labelDisplayedRows={({ from, to, count }) =>
                `${from}–${to} of ${count !== -1 ? count.toLocaleString() : `more than ${to}`}`
              }
              sx={{ borderBottom: 1, borderColor: 'divider', mb: 1 }}
            />
          ) : null}
          {isLoading ? (
            <Typography variant="body2">Loading…</Typography>
          ) : (data?.items ?? []).length === 0 ? (
            <Alert severity="info">
              No distributor inventory rows for this selection. Confirm DSI inventory snapshots exist for this
              distributor (Admin → Imports), or try another distributor.
            </Alert>
          ) : (
            <Table size="small">
              <TableHead>
                <TableRow>
                  <TableCell>Product</TableCell>
                  <TableCell>SKU</TableCell>
                  <TableCell align="right">Reported SOH</TableCell>
                  <TableCell align="right">Derived stock</TableCell>
                  {depthAtLeast(depth, 'operational') && (
                    <>
                      <TableCell align="right">Calculated SOH</TableCell>
                      <TableCell align="right">Variance</TableCell>
                      <TableCell>Recon status</TableCell>
                    </>
                  )}
                  {depthAtLeast(depth, 'strategic') && (
                    <>
                      <TableCell align="right">Velocity 52wk</TableCell>
                      <TableCell align="right">Weeks of cover</TableCell>
                    </>
                  )}
                  {depthAtLeast(depth, 'forecast') && <TableCell>Reorder</TableCell>}
                </TableRow>
              </TableHead>
              <TableBody>
                {(data?.items ?? []).map((r) => (
                  <TableRow key={r.product_id}>
                    <TableCell>{r.product_name}</TableCell>
                    <TableCell>{r.sku}</TableCell>
                    <TableCell align="right">{r.reported_soh.toLocaleString()}</TableCell>
                    <TableCell align="right">
                      {(r.derived_stock ?? r.reported_soh).toLocaleString()}
                    </TableCell>
                    {depthAtLeast(depth, 'operational') && (
                      <>
                        <TableCell align="right">
                          {r.calculated_soh != null ? r.calculated_soh.toLocaleString() : '—'}
                        </TableCell>
                        <TableCell align="right">
                          {r.variance_units != null ? r.variance_units.toLocaleString() : '—'}
                        </TableCell>
                        <TableCell>{r.reconciliation_status ?? '—'}</TableCell>
                      </>
                    )}
                    {depthAtLeast(depth, 'strategic') && (
                      <>
                        <TableCell align="right">
                          {r.velocity_52wk != null ? r.velocity_52wk.toFixed(2) : '—'}
                        </TableCell>
                        <TableCell align="right">
                          {r.weeks_of_cover != null ? r.weeks_of_cover.toFixed(1) : 'n/a'}
                        </TableCell>
                      </>
                    )}
                    {depthAtLeast(depth, 'forecast') && (
                      <TableCell>
                        {r.reorder_signal ? (
                          <WarningAmberIcon color="warning" fontSize="small" titleAccess="Reorder signal" />
                        ) : (
                          '—'
                        )}
                      </TableCell>
                    )}
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </Box>
      </Paper>
    </Box>
  );
}
