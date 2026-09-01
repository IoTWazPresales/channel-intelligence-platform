'use client';

import { Box, Typography } from '@mui/material';
import { alpha, useTheme } from '@mui/material/styles';
import { useQuery } from '@tanstack/react-query';

import { formatUnits, type LineupPlanRow, type NetRequirementResponse } from '@/features/lineup/lineupTypes';
import { apiGet } from '@/lib/api';

function computeRegime(rows: LineupPlanRow[], netReq: NetRequirementResponse | undefined) {
  const plannedUnits = rows.reduce((s, r) => s + (Number(r.planned_volume_units) || 0), 0);
  const decided = rows.filter((r) => r.approval_status === 'approved' || r.approval_status === 'rejected');
  const approved = rows.filter((r) => r.approval_status === 'approved').length;
  const approvalPct = decided.length > 0 ? Math.round((approved / decided.length) * 100) : rows.length ? 0 : 0;
  const netTotal =
    netReq?.data_unavailable === false
      ? Math.round((netReq.rows ?? []).reduce((s, r) => s + (r.net_requirement || 0), 0))
      : null;
  return { plannedUnits, approvalPct, netTotal };
}

export function LineupRegimeStrip() {
  const theme = useTheme();

  const { data: items } = useQuery({
    queryKey: ['lineup-items'],
    queryFn: ({ signal }) => apiGet<LineupPlanRow[]>('/api/v1/lineup/items', { signal }),
    staleTime: 30_000,
  });

  const { data: netReq } = useQuery({
    queryKey: ['lineup-net-requirement', 'regime'],
    queryFn: ({ signal }) =>
      apiGet<NetRequirementResponse>(
        '/api/v1/lineup/net-requirement?limit=200&include_customer_shares=false&apply_bias=true',
        { signal },
      ),
    staleTime: 60_000,
  });

  const rows = items ?? [];
  const { plannedUnits, approvalPct, netTotal } = computeRegime(rows, netReq);

  const tiles = [
    { label: 'Planned units', value: rows.length ? formatUnits(plannedUnits) : '—' },
    { label: 'Net requirement (B2)', value: netTotal != null ? formatUnits(netTotal) : '—' },
    { label: 'Approval', value: rows.length ? `${approvalPct}%` : '—' },
  ];

  return (
    <Box
      data-testid="lineup-regime-strip"
      sx={{ display: 'flex', gap: 3.25, ml: 'auto', flexWrap: 'wrap', justifyContent: 'flex-end' }}
    >
      {tiles.map((t) => (
        <Box key={t.label} sx={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-end', gap: 0.25 }}>
          <Typography
            sx={{ fontSize: '9.5px', letterSpacing: '0.09em', textTransform: 'uppercase', color: alpha(theme.palette.text.primary, 0.45) }}
          >
            {t.label}
          </Typography>
          <Typography sx={{ fontFamily: '"IBM Plex Mono", monospace', fontSize: '13px', color: alpha(theme.palette.text.primary, 0.72) }}>
            {t.value}
          </Typography>
        </Box>
      ))}
    </Box>
  );
}
