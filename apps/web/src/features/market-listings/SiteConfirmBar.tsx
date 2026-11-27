'use client';

import { Alert, Button, Stack, Typography } from '@mui/material';

import { discoveryError, useDecideSiteCandidate, useSiteCandidates } from './discoveryApi';

/**
 * Compact confirm/reject for proposed sites. Mounted on Monitored listings only,
 * immediately above the price matrix. Step 3 tracker.
 */
export function SiteConfirmBar() {
  const queue = useSiteCandidates();
  const decide = useDecideSiteCandidate();
  const items = queue.data?.items ?? [];
  if (!queue.isPending && !queue.isError && items.length === 0) return null;
  return (
    <Stack
      direction={{ xs: 'column', sm: 'row' }}
      spacing={1}
      useFlexGap
      flexWrap="wrap"
      alignItems="center"
      data-testid="site-confirm-bar"
    >
      {queue.isPending ? <Typography variant="body2">Loading sites to confirm…</Typography> : null}
      {queue.isError ? (
        <Alert severity="error" action={<Button color="inherit" onClick={() => void queue.refetch()}>Retry</Button>}>
          {discoveryError(queue.error)}
        </Alert>
      ) : null}
      {items.map((item) => (
        <Stack key={item.id} direction="row" spacing={0.5} alignItems="center">
          <Typography variant="body2">{item.customer_name} · {item.domain}</Typography>
          <Button
            size="small"
            variant="contained"
            disabled={decide.isPending}
            onClick={() => decide.mutate({ id: item.id, action: 'confirm' })}
          >
            Confirm
          </Button>
          <Button
            size="small"
            variant="outlined"
            disabled={decide.isPending}
            onClick={() => decide.mutate({ id: item.id, action: 'reject' })}
          >
            Reject
          </Button>
        </Stack>
      ))}
    </Stack>
  );
}
