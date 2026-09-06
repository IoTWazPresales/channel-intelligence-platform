'use client';

import { Typography } from '@mui/material';

import { HeadlineFigure, HeadlineStrip } from '@/features/workbench-ui/HeadlineFigure';
import { useQuery } from '@tanstack/react-query';

import { apiGet } from '@/lib/api';

import type { StewardshipSummary } from './types';
import { useClientReady } from './useClientReady';

export function StewardQueueOverview() {
  const ready = useClientReady();
  const { data: summary } = useQuery({
    queryKey: ['imports', 'stewardship-summary'],
    queryFn: ({ signal }) => apiGet<StewardshipSummary>('/api/v1/imports/stewardship-summary', { signal }),
    staleTime: 30_000,
  });
  const data = ready ? summary : undefined;
  return (
    <>
      <HeadlineStrip columns={4}>
        <HeadlineFigure
          label="Legacy queue rows"
          value={data?.legacy_queue_open ?? '—'}
          compact
          severity={data?.legacy_queue_open ? 'warn' : 'good'}
          caption={data?.captions.legacy_queue_open}
        />
        <HeadlineFigure label="Customer-like candidates" value={data?.candidates_customerish ?? '—'} compact />
        <HeadlineFigure label="Product candidates" value={data?.candidates_productish ?? '—'} compact />
        <HeadlineFigure label="Distributor candidates" value={data?.candidates_distributorish ?? '—'} compact />
      </HeadlineStrip>
      <Typography variant="body2" color="text.secondary" sx={{ mt: 1, mb: 2 }}>
        This leaf is the legacy mapping queue (D-0002 untouched). Per-job stewarding stays inside each import job.
        Candidate counts are open <code>needs_review</code> rows across jobs — they are not this grid unless you open a
        job with <code>?import_job_id=</code>. Cross-job accept/reject named by CONSULT is not on this surface.
      </Typography>
    </>
  );
}
