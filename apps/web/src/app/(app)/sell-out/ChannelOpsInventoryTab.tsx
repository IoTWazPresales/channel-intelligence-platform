'use client';

import WarningAmberIcon from '@mui/icons-material/WarningAmber';
import {
  Alert,
  Autocomplete,
  Box,
  Paper,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableRow,
  TextField,
  Typography,
} from '@mui/material';
import { useQuery } from '@tanstack/react-query';
import { useState } from 'react';

import { apiGet } from '@/lib/api';

import { depthAtLeast, type IntelDepth } from './intelDepth';

type DistHit = { id: number; distributor_code: string; distributor_name: string };

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

export function ChannelOpsInventoryTab({ depth }: { depth: IntelDepth }) {
  const [distributorPick, setDistributorPick] = useState<DistHit | null>(null);

  const { data: filterOptions } = useQuery({
    queryKey: ['sellout-filter-options'],
    queryFn: ({ signal }) =>
      apiGet<{ distributors: DistHit[] }>('/api/v1/sellout/filter-options', { signal }),
  });

  const distId = distributorPick?.id;
  const { data, isLoading, isError, error } = useQuery({
    queryKey: ['channel-ops-inventory', distId],
    queryFn: ({ signal }) =>
      apiGet<{ items: InvRow[]; total: number; truncated?: boolean }>(
        `/api/v1/channel-ops/inventory?distributor_id=${distId}`,
        { signal }
      ),
    enabled: distId != null,
  });

  if (distId == null) {
    return (
      <Box>
        <Stack direction="row" spacing={2} sx={{ mb: 2 }} flexWrap="wrap" useFlexGap>
          <Autocomplete
            sx={{ minWidth: 320 }}
            size="small"
            options={filterOptions?.distributors ?? []}
            value={distributorPick}
            onChange={(_e, v) => setDistributorPick(v)}
            getOptionLabel={(o) => `${o.distributor_name} (${o.distributor_code})`}
            isOptionEqualToValue={(a, b) => a.id === b.id}
            renderInput={(params) => <TextField {...params} label="Distributor" required />}
          />
        </Stack>
        <Alert severity="info">
          Select a distributor to view inventory intelligence for that channel.
        </Alert>
      </Box>
    );
  }

  return (
    <Box>
      <Stack direction="row" spacing={2} sx={{ mb: 2 }} flexWrap="wrap" useFlexGap>
        <Autocomplete
          sx={{ minWidth: 320 }}
          size="small"
          options={filterOptions?.distributors ?? []}
          value={distributorPick}
          onChange={(_e, v) => setDistributorPick(v)}
          getOptionLabel={(o) => `${o.distributor_name} (${o.distributor_code})`}
          isOptionEqualToValue={(a, b) => a.id === b.id}
          renderInput={(params) => <TextField {...params} label="Distributor" required />}
        />
      </Stack>
      {isError && (
        <Alert severity="error" sx={{ mb: 2 }}>
          {(error as Error)?.message ?? 'Failed to load inventory.'}
        </Alert>
      )}
      {data?.truncated ? (
        <Alert severity="warning" sx={{ mb: 2 }}>
          Showing first {data.items.length.toLocaleString()} of {data.total.toLocaleString()} products for this
          distributor. Server cap applies until inventory paging is added.
        </Alert>
      ) : null}
      <Paper variant="outlined">
        <Box sx={{ p: 2 }}>
          {isLoading ? (
            <Typography variant="body2">Loading…</Typography>
          ) : (data?.items ?? []).length === 0 ? (
            <Typography variant="body2" color="text.secondary">
              No distributor inventory rows for this selection.
            </Typography>
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
