'use client';

import { Box, CircularProgress, Paper, Stack, Table, TableBody, TableCell, TableHead, TableRow, Typography } from '@mui/material';
import { alpha, useTheme } from '@mui/material/styles';
import { useQuery } from '@tanstack/react-query';

import { ReadStrip } from '@/features/shell/ReadStrip';
import { WOC_BUCKET_LABELS, type WocBucketId } from '@/features/stock/stockLenses';
import { apiGet } from '@/lib/api';

type CoverDistribution = {
  data_unavailable?: boolean;
  pair_count: number;
  under_4w: number;
  mean_woc: number | null;
  buckets: Record<WocBucketId, number>;
  cover_as_of_date?: string | null;
  items?: {
    distributor_id: number;
    product_id: number;
    weeks_of_cover: number | null;
    derived_stock: number;
    replenishment_flag: boolean;
  }[];
};

const BUCKET_ORDER: WocBucketId[] = ['lt2', '2to4', '4to8', '8to13', 'gte13'];

function bucketBarColor(id: WocBucketId): string {
  if (id === 'lt2') return 'rgba(196,92,92,0.78)';
  if (id === '2to4') return 'rgba(212,161,90,0.72)';
  return 'rgba(61,155,106,0.55)';
}

export function CoverLensView() {
  const theme = useTheme();
  const line = alpha(theme.palette.common.white, 0.12);

  const { data, isLoading, isError } = useQuery({
    queryKey: ['channel-ops', 'cover-distribution'],
    queryFn: ({ signal }) => apiGet<CoverDistribution>('/api/v1/channel-ops/cover-distribution', { signal }),
    staleTime: 60_000,
  });

  if (isLoading) {
    return (
      <Box sx={{ display: 'grid', placeItems: 'center', py: 6 }} data-testid="stock-cover-loading">
        <CircularProgress size={28} />
      </Box>
    );
  }

  if (isError || !data || data.data_unavailable) {
    return (
      <Box sx={{ p: 2 }} data-testid="stock-cover-empty">
        <Typography color="text.secondary" sx={{ fontSize: '13px' }}>
          Cover distribution is not available yet — import distributor inventory (DSI) and run cover observations.
        </Typography>
      </Box>
    );
  }

  const cover = data;
  const maxBucket = Math.max(...BUCKET_ORDER.map((b) => cover.buckets[b] ?? 0), 1);
  const readText =
    cover.under_4w > 0
      ? `**${cover.under_4w} of ${cover.pair_count} pairs** sit under 4 weeks of cover` +
        (cover.mean_woc != null ? ` while the book averages **${cover.mean_woc} weeks**.` : '.')
      : `**${cover.pair_count} pairs** on cover tape` +
        (cover.mean_woc != null ? ` — book mean **${cover.mean_woc} weeks**.` : '.');

  return (
    <Box data-testid="stock-cover-lens">
      <ReadStrip text={readText} />
      <Box sx={{ px: 2.75, py: 1.75, bgcolor: '#1a1d23', borderBottom: `1px solid ${line}` }}>
        <Stack direction="row" justifyContent="space-between" alignItems="baseline" sx={{ mb: 1.25 }}>
          <Typography sx={{ fontSize: '9.5px', letterSpacing: '0.08em', textTransform: 'uppercase', color: alpha(theme.palette.text.primary, 0.45) }}>
            Pairs by weeks of cover
          </Typography>
          <Typography sx={{ fontFamily: '"IBM Plex Mono", monospace', fontSize: '10.5px', color: alpha(theme.palette.text.primary, 0.45) }}>
            {cover.pair_count} pairs
            {cover.mean_woc != null ? (
              <>
                {' '}
                · mean <Box component="span" sx={{ color: alpha(theme.palette.text.primary, 0.72), fontWeight: 500 }}>{cover.mean_woc}w</Box>
              </>
            ) : null}
          </Typography>
        </Stack>
        <Box
          sx={{
            display: 'grid',
            gridTemplateColumns: 'repeat(5, 1fr)',
            gap: 1,
            alignItems: 'end',
            height: 86,
            mb: 0.75,
          }}
        >
          {BUCKET_ORDER.map((id) => {
            const count = cover.buckets[id] ?? 0;
            const height = Math.max(8, Math.round((count / maxBucket) * 72));
            return (
              <Box key={id} sx={{ display: 'flex', flexDirection: 'column', justifyContent: 'flex-end', height: '100%' }}>
                <Box sx={{ width: '100%', height, borderRadius: '1px 1px 0 0', bgcolor: bucketBarColor(id) }} />
              </Box>
            );
          })}
        </Box>
        <Box sx={{ display: 'grid', gridTemplateColumns: 'repeat(5, 1fr)', gap: 1, mt: 0.75 }}>
          {BUCKET_ORDER.map((id) => (
            <Typography
              key={id}
              sx={{
                textAlign: 'center',
                fontFamily: '"IBM Plex Mono", monospace',
                fontSize: '10px',
                color: alpha(theme.palette.text.primary, 0.45),
                lineHeight: 1.35,
              }}
            >
              {WOC_BUCKET_LABELS[id]}
              <Box component="span" sx={{ display: 'block', color: alpha(theme.palette.text.primary, 0.72), fontWeight: 500 }}>
                {cover.buckets[id] ?? 0}
              </Box>
            </Typography>
          ))}
        </Box>
      </Box>
      <Paper variant="outlined" sx={{ m: 2, borderColor: line }}>
        <Box sx={{ overflow: 'auto', maxHeight: 420 }}>
          <Table size="small" stickyHeader>
            <TableHead>
              <TableRow>
                <TableCell>Dist #</TableCell>
                <TableCell>Product #</TableCell>
                <TableCell align="right">WOC</TableCell>
                <TableCell align="right">Derived stock</TableCell>
                <TableCell>Replenish</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {(cover.items ?? []).slice(0, 100).map((row) => (
                <TableRow key={`${row.distributor_id}-${row.product_id}`}>
                  <TableCell>{row.distributor_id}</TableCell>
                  <TableCell>{row.product_id}</TableCell>
                  <TableCell
                    align="right"
                    sx={{
                      fontFamily: '"IBM Plex Mono", monospace',
                      color: (row.weeks_of_cover ?? 99) < 4 ? '#e8b4b4' : undefined,
                      fontWeight: (row.weeks_of_cover ?? 99) < 4 ? 600 : 400,
                    }}
                  >
                    {row.weeks_of_cover != null ? `${row.weeks_of_cover.toFixed(1)}w` : '—'}
                  </TableCell>
                  <TableCell align="right" sx={{ fontFamily: '"IBM Plex Mono", monospace' }}>
                    {Math.round(row.derived_stock).toLocaleString()}
                  </TableCell>
                  <TableCell>{row.replenishment_flag ? 'Yes' : '—'}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </Box>
      </Paper>
    </Box>
  );
}
