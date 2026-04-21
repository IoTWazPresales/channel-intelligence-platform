'use client';

import ExpandMoreIcon from '@mui/icons-material/ExpandMore';
import {
  Accordion,
  AccordionDetails,
  AccordionSummary,
  Box,
  Chip,
  LinearProgress,
  Stack,
  Typography,
} from '@mui/material';
import { alpha, keyframes } from '@mui/material/styles';
import { useEffect, useMemo, useRef, useState } from 'react';

export type PmProgressRailStep = {
  id: string;
  label: string;
  description: string;
  state: 'complete' | 'current' | 'waiting' | 'failed';
};

export type PmProgressSnapshot = {
  phase_id: string;
  phase_label: string;
  phase_description: string;
  rail_index: number;
  step_count: number;
  steps: PmProgressRailStep[];
  job_stage: string;
  job_status: string;
  validation_passed: boolean | null;
  total_rows: number | null | undefined;
  staged_row_count: number;
  row_result_info: number;
  row_result_warnings: number;
  row_result_errors: number;
  error_summary?: string | null;
  started_at?: string | null;
  updated_at?: string | null;
  completed_at?: string | null;
  /** queued | running | failed when async Product Master commit is active */
  commit_async_phase?: string | null;
};

const pulse = keyframes`
  0% { opacity: 0.55; }
  50% { opacity: 1; }
  100% { opacity: 0.55; }
`;

export type PmImportProgressPanelProps = {
  progress: PmProgressSnapshot | null | undefined;
  /** Raw import_job.status (commit_queued / commit_running / …) */
  jobStatus?: string | null;
  isValidating: boolean;
  isCommitting: boolean;
  isSavingMapping?: boolean;
};

function formatElapsed(seconds: number): string {
  if (seconds < 60) return `${seconds}s`;
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  return `${m}m ${s}s`;
}

export function PmImportProgressPanel({
  progress,
  jobStatus,
  isValidating,
  isCommitting,
  isSavingMapping,
}: PmImportProgressPanelProps) {
  const asyncCommitPending =
    jobStatus === 'commit_queued' || jobStatus === 'commit_running';
  const busy =
    isValidating || isCommitting || Boolean(isSavingMapping) || asyncCommitPending;
  const startRef = useRef<number | null>(null);
  const [tick, setTick] = useState(0);

  useEffect(() => {
    if (busy) {
      if (startRef.current == null) startRef.current = Date.now();
    } else {
      startRef.current = null;
    }
  }, [busy]);

  useEffect(() => {
    if (!busy) return;
    const id = window.setInterval(() => setTick((t) => t + 1), 1000);
    return () => window.clearInterval(id);
  }, [busy]);

  const elapsedSec =
    busy && startRef.current != null
      ? Math.max(0, Math.floor((Date.now() - startRef.current) / 1000))
      : null;
  void tick;

  const phaseTitle = useMemo(() => {
    if (isSavingMapping) return 'Saving mapping';
    if (isValidating) return 'Validating';
    if (isCommitting) return 'Enqueueing commit';
    if (jobStatus === 'commit_running') return 'Committing (background worker)';
    if (jobStatus === 'commit_queued') return 'Commit queued';
    return progress?.phase_label ?? 'Import status';
  }, [isCommitting, isSavingMapping, isValidating, jobStatus, progress?.phase_label]);

  const phaseDescription = useMemo(() => {
    if (isSavingMapping) return 'Updating column mapping on the server…';
    if (isValidating) return 'Running row checks and building staged metadata. Safe to wait — this can take a while on large files.';
    if (isCommitting) return 'Sending the commit job to the worker…';
    if (jobStatus === 'commit_running') {
      return (
        progress?.phase_description ||
        'The worker is writing dim_product and catalog rows. This can take several minutes for large files.'
      );
    }
    if (jobStatus === 'commit_queued') {
      return 'Your commit is in the queue and will start when the worker picks it up.';
    }
    return progress?.phase_description ?? '';
  }, [isCommitting, isSavingMapping, isValidating, jobStatus, progress?.phase_description]);

  const steps = progress?.steps ?? [];

  return (
    <Box
      sx={{
        borderRadius: 2,
        p: 2.5,
        mb: 2,
        border: '1px solid',
        borderColor: (t) => alpha(t.palette.divider, 0.9),
        background: (t) =>
          `linear-gradient(165deg, ${alpha(t.palette.primary.main, 0.04)} 0%, ${alpha(t.palette.background.paper, 1)} 42%)`,
        boxShadow: (t) => `0 1px 0 ${alpha(t.palette.common.black, 0.04)}`,
      }}
    >
      <Stack spacing={2}>
        <Stack direction="row" justifyContent="space-between" alignItems="flex-start" flexWrap="wrap" useFlexGap>
          <Box sx={{ minWidth: 200, flex: 1 }}>
            <Typography variant="overline" color="text.secondary" sx={{ letterSpacing: 0.12, fontWeight: 600 }}>
              Product Master import
            </Typography>
            <Typography variant="h6" sx={{ fontWeight: 600, mt: 0.25 }}>
              {phaseTitle}
            </Typography>
            <Typography variant="body2" color="text.secondary" sx={{ mt: 0.5, maxWidth: 640 }}>
              {phaseDescription}
            </Typography>
          </Box>
          <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap" useFlexGap>
            {busy ? (
              <Chip
                size="small"
                label="In progress"
                color="primary"
                variant="outlined"
                sx={{ animation: `${pulse} 1.6s ease-in-out infinite` }}
              />
            ) : null}
            {progress?.job_status ? (
              <Chip size="small" label={progress.job_status} variant="outlined" />
            ) : null}
            {elapsedSec != null ? (
              <Typography variant="caption" color="text.secondary">
                Elapsed {formatElapsed(elapsedSec)}
              </Typography>
            ) : null}
          </Stack>
        </Stack>

        {busy ? (
          <LinearProgress
            variant="indeterminate"
            sx={{
              height: 4,
              borderRadius: 99,
              bgcolor: (t) => alpha(t.palette.primary.main, 0.12),
              '& .MuiLinearProgress-bar': { borderRadius: 99 },
            }}
          />
        ) : (
          <LinearProgress
            variant="determinate"
            value={
              progress && progress.step_count > 1
                ? Math.min(100, (progress.rail_index / (progress.step_count - 1)) * 100)
                : 0
            }
            sx={{
              height: 4,
              borderRadius: 99,
              bgcolor: (t) => alpha(t.palette.text.primary, 0.06),
              '& .MuiLinearProgress-bar': { borderRadius: 99 },
            }}
          />
        )}

        <Stack direction="row" spacing={0.5} flexWrap="wrap" useFlexGap sx={{ pt: 0.5 }}>
          {steps.map((s, i) => {
            const isLast = i === steps.length - 1;
            const color =
              s.state === 'complete'
                ? 'success.main'
                : s.state === 'failed'
                  ? 'error.main'
                  : s.state === 'current'
                    ? 'primary.main'
                    : 'text.disabled';
            const bg =
              s.state === 'complete'
                ? 'success.main'
                : s.state === 'failed'
                  ? 'error.main'
                  : s.state === 'current'
                    ? 'primary.main'
                    : 'action.hover';
            return (
              <Stack key={s.id} direction="row" alignItems="center" sx={{ flex: isLast ? '0 0 auto' : '1 1 0', minWidth: 0 }}>
                <Stack alignItems="center" sx={{ flex: 1, minWidth: 0 }}>
                  <Box
                    sx={{
                      width: 10,
                      height: 10,
                      borderRadius: '50%',
                      bgcolor: bg,
                      opacity: s.state === 'waiting' ? 0.35 : 1,
                      boxShadow: s.state === 'current' ? (t) => `0 0 0 4px ${alpha(t.palette.primary.main, 0.2)}` : 'none',
                      transition: 'box-shadow 0.25s ease, opacity 0.25s ease',
                    }}
                  />
                  <Typography variant="caption" sx={{ mt: 0.5, fontWeight: s.state === 'current' ? 600 : 500, color, textAlign: 'center' }}>
                    {s.label}
                  </Typography>
                </Stack>
                {!isLast ? (
                  <Box
                    sx={{
                      flex: 1,
                      height: 2,
                      mx: 0.5,
                      mb: 2,
                      borderRadius: 99,
                      bgcolor: (t) => alpha(t.palette.text.primary, i < (progress?.rail_index ?? -1) ? 0.18 : 0.08),
                      minWidth: 8,
                    }}
                  />
                ) : null}
              </Stack>
            );
          })}
        </Stack>

        <Accordion disableGutters elevation={0} sx={{ bgcolor: 'transparent', '&:before': { display: 'none' } }}>
          <AccordionSummary expandIcon={<ExpandMoreIcon fontSize="small" />}>
            <Typography variant="caption" color="text.secondary" fontWeight={600}>
              Details &amp; counts
            </Typography>
          </AccordionSummary>
          <AccordionDetails>
            <Stack spacing={0.75}>
              <Typography variant="body2" color="text.secondary">
                <strong>Rows in file:</strong> {progress?.total_rows ?? '—'}
              </Typography>
              <Typography variant="body2" color="text.secondary">
                <strong>Staged metadata rows:</strong> {progress?.staged_row_count ?? 0}
              </Typography>
              <Typography variant="body2" color="text.secondary">
                <strong>Import messages:</strong> info {progress?.row_result_info ?? 0}, warnings{' '}
                {progress?.row_result_warnings ?? 0}, errors {progress?.row_result_errors ?? 0}
              </Typography>
              {progress?.error_summary ? (
                <Typography variant="body2" color="warning.main">
                  <strong>Summary:</strong> {progress.error_summary}
                </Typography>
              ) : null}
              <Typography variant="caption" color="text.secondary" component="div">
                Stage: {progress?.job_stage ?? '—'} · Last update: {progress?.updated_at ?? '—'}
              </Typography>
            </Stack>
          </AccordionDetails>
        </Accordion>
      </Stack>
    </Box>
  );
}
