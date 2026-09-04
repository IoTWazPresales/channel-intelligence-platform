'use client';

import { Box, CircularProgress, Typography } from '@mui/material';
import { alpha, useTheme } from '@mui/material/styles';
import { useQuery } from '@tanstack/react-query';

import { BriefEmptyState, BriefSignalRow, type BriefSignal } from '@/features/brief/BriefSignalRow';
import { ReadStrip } from '@/features/shell/ReadStrip';
import { apiGet } from '@/lib/api';

type BriefSignalsResponse = {
  as_of: string;
  read: string;
  signals: BriefSignal[];
  signal_count?: number;
};

function formatBriefFooterAsOf(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  const datePart = d.toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' });
  const timePart = d.toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit', hour12: false });
  return `${datePart} · ${timePart}`;
}

export function BriefPageContent() {
  const theme = useTheme();
  const line = alpha(theme.palette.common.white, 0.12);

  const { data, isLoading, isError } = useQuery({
    queryKey: ['brief', 'signals'],
    queryFn: ({ signal }) => apiGet<BriefSignalsResponse>('/api/v1/brief/signals', { signal }),
    staleTime: 30_000,
  });

  if (isLoading) {
    return (
      <Box sx={{ flex: 1, display: 'grid', placeItems: 'center', py: 8 }} data-testid="brief-loading">
        <CircularProgress size={32} />
      </Box>
    );
  }

  if (isError) {
    return (
      <Box sx={{ p: 3 }} data-testid="brief-error">
        <Typography color="error">Could not load attention signals.</Typography>
      </Box>
    );
  }

  const signals = data?.signals ?? [];

  const signalCount = data?.signal_count ?? signals.length;

  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', flex: 1, minHeight: 0 }} data-testid="brief-page">
      <Box
        sx={{
          display: 'flex',
          alignItems: 'baseline',
          justifyContent: 'space-between',
          gap: 1,
          px: 2.75,
          py: 1.25,
          borderBottom: `1px solid ${line}`,
        }}
      >
        <Typography sx={{ fontSize: '12px', color: alpha(theme.palette.text.primary, 0.5) }}>
          <Box component="span" sx={{ color: alpha(theme.palette.text.primary, 0.72), fontWeight: 500 }}>
            Attention
          </Box>{' '}
          · what needs action now
        </Typography>
      </Box>
      {signals.length > 0 && data?.read ? <ReadStrip text={data.read} /> : null}
      <Box sx={{ flex: 1, overflow: 'auto' }}>
        {signals.length > 0 ? signals.map((sig) => <BriefSignalRow key={sig.id} signal={sig} />) : <BriefEmptyState />}
      </Box>
      {data?.as_of ? (
        <Box
          data-testid="brief-footer"
          sx={{
            display: 'flex',
            alignItems: 'baseline',
            gap: 2.25,
            px: 2.75,
            py: 1,
            borderTop: `1px solid ${line}`,
            fontFamily: '"IBM Plex Mono", monospace',
            fontSize: '11px',
            color: alpha(theme.palette.text.primary, 0.5),
          }}
        >
          <span>
            {signalCount} signal{signalCount === 1 ? '' : 's'} · ranked trust → position → money
          </span>
          <Box component="span" sx={{ ml: 'auto' }}>
            Updated {formatBriefFooterAsOf(data.as_of)}
          </Box>
        </Box>
      ) : null}
    </Box>
  );
}
