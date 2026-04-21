'use client';

import { Alert, Paper, Typography } from '@mui/material';
import { useQuery } from '@tanstack/react-query';

import { PageHeader } from '@/components/PageHeader';
import { apiGet } from '@/lib/api';

export default function MarketPage() {
  const { data } = useQuery({
    queryKey: ['market-placeholders'],
    queryFn: ({ signal }) => apiGet<Record<string, unknown>>('/api/v1/market/placeholders', { signal }),
  });

  return (
    <>
      <PageHeader crumbs={[{ label: 'Market' }]} title="External market context" />
      <Typography variant="body2" color="text.secondary" sx={{ mb: 2, maxWidth: 900 }}>
        The API currently returns a <strong>static JSON stub</strong> (not an empty grid)—syndicated panel, share, and
        macro feeds are not connected yet. Treat this page as a contract preview for future integrations.
      </Typography>
      <Alert severity="info" sx={{ mb: 2 }}>
        When real feeds exist, this view will switch to charts/tables with the same theme as the rest of the app.
      </Alert>
      <Paper sx={{ p: 2 }}>
        <Typography variant="body2" component="pre" sx={{ whiteSpace: 'pre-wrap', m: 0 }}>
          {JSON.stringify(data, null, 2)}
        </Typography>
      </Paper>
    </>
  );
}
