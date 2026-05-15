'use client';

import { Alert, LinearProgress, Stack, Typography } from '@mui/material';
import { useMemo } from 'react';

import { useBackgroundTasks } from './BackgroundTasksProvider';

function idsMatch(t: { import_job_id?: number | null; related_import_job_ids?: number[] }, jobId: number): boolean {
  if (t.import_job_id != null && Number(t.import_job_id) === jobId) return true;
  const rel = t.related_import_job_ids;
  if (Array.isArray(rel) && rel.map(Number).includes(jobId)) return true;
  return false;
}

type Props = {
  importJobId: number | null;
  /** imports page: PM + shipment reresolution for this job; shipment page: reresolution only */
  mode: 'imports' | 'shipment-evidence';
};

export function PageTaskBanner({ importJobId, mode }: Props) {
  const { tasks } = useBackgroundTasks();

  const active = useMemo(() => {
    if (importJobId == null) return null;
    return tasks.find((t) => {
      if (t.status !== 'running' && t.status !== 'queued') return false;
      if (!idsMatch(t, importJobId)) return false;
      if (mode === 'shipment-evidence' && t.type === 'product_master_commit') return false;
      return true;
    });
  }, [tasks, importJobId, mode]);

  if (!active) return null;

  const line = String(active.summary || active.title || '').trim();
  const pct =
    active.lines_total && active.lines_processed != null && active.lines_total > 0
      ? Math.min(100, (Number(active.lines_processed) / Number(active.lines_total)) * 100)
      : null;

  return (
    <Alert severity={active.status === 'failed' ? 'error' : 'info'} sx={{ mb: 2, alignItems: 'flex-start' }}>
      <Stack spacing={1} sx={{ width: '100%', minWidth: 0 }}>
        <Typography variant="body2" fontWeight={600}>
          {active.title}
        </Typography>
        <Typography variant="body2" color="text.secondary" sx={{ wordBreak: 'break-word' }}>
          {line}
        </Typography>
        {pct != null ? <LinearProgress variant="determinate" value={pct} sx={{ borderRadius: 1, maxWidth: 480 }} /> : null}
      </Stack>
    </Alert>
  );
}
