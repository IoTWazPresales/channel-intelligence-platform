'use client';

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
import ExpandMoreIcon from '@mui/icons-material/ExpandMore';
import { alpha, keyframes } from '@mui/material/styles';
import { useEffect, useRef, useState } from 'react';

export type DsiValidateProgress = {
  job_id?: number;
  stage?: string;
  status?: string;
  phase?: string;
  phase_label?: string;
  current_row?: number;
  total_rows?: number;
  pct?: number;
  task_state?: string | null;
  pipeline_queued_at?: string | null;
  pipeline_started_at?: string | null;
};

const DSI_PROGRESS_PHASES = [
  { id: 'loading_caches', label: 'Load caches' },
  { id: 'processing_rows', label: 'Process rows' },
  { id: 'building_candidates', label: 'Build candidates' },
  { id: 'complete', label: 'Complete' },
] as const;

type PhaseId = (typeof DSI_PROGRESS_PHASES)[number]['id'];

const PHASE_ORDER: PhaseId[] = DSI_PROGRESS_PHASES.map((p) => p.id);

const pulse = keyframes`
  0% { opacity: 0.55; }
  50% { opacity: 1; }
  100% { opacity: 0.55; }
`;

function formatElapsed(seconds: number): string {
  if (seconds < 60) return `${seconds}s`;
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  return `${m}m ${s}s`;
}

function formatNum(n: number): string {
  return n.toLocaleString();
}

export type DsiValidateProgressPanelProps = {
  progress: DsiValidateProgress | null | undefined;
  isRunning: boolean;
};

export function DsiValidateProgressPanel({ progress, isRunning }: DsiValidateProgressPanelProps) {
  const startRef = useRef<number | null>(null);
  const [tick, setTick] = useState(0);

  useEffect(() => {
    if (isRunning) {
      if (startRef.current == null) startRef.current = Date.now();
    } else {
      startRef.current = null;
    }
  }, [isRunning]);

  useEffect(() => {
    if (!isRunning) return;
    const id = window.setInterval(() => setTick((t) => t + 1), 1000);
    return () => window.clearInterval(id);
  }, [isRunning]);

  void tick;

  const elapsedSec =
    isRunning && startRef.current != null
      ? Math.max(0, Math.floor((Date.now() - startRef.current) / 1000))
      : null;

  const rawPhase = (progress?.phase ?? (isRunning ? 'processing_rows' : 'idle')) as PhaseId | 'idle' | 'failed';
  const phaseLabel = progress?.phase_label ?? (isRunning ? 'Processing rows' : 'Waiting');
  const currentRow = progress?.current_row ?? 0;
  const totalRows = progress?.total_rows ?? 0;
  const pct = progress?.pct ?? 0;
  const hasDeterminate = pct > 0 && totalRows > 0 && rawPhase !== 'loading_caches';

  const currentPhaseIndex = PHASE_ORDER.indexOf(rawPhase as PhaseId);

  const queuedAt = progress?.pipeline_queued_at;
  const startedAt = progress?.pipeline_started_at;
  const queueWaitLabel =
    queuedAt && !startedAt && rawPhase === 'queued'
      ? 'Waiting for worker to pick up the task…'
      : queuedAt && startedAt
        ? null
        : null;

  const phaseDescription =
    rawPhase === 'loading_caches'
      ? 'Pre-loading entity resolution caches (distributors, products, customers). This is a one-time cost per job.'
      : rawPhase === 'processing_rows'
        ? totalRows > 0
          ? `Running row-level entity resolution and corroboration checks. ${formatNum(totalRows)} rows in this file.`
          : 'Running row-level entity resolution and corroboration checks against your import file.'
        : rawPhase === 'building_candidates'
          ? 'Aggregating ambiguous entity tokens into steward review candidates.'
          : rawPhase === 'complete' || rawPhase === 'failed'
            ? ''
            : 'Initialising validation pipeline…';

  return (
    <Box
      sx={{
        borderRadius: 2,
        p: 2.5,
        border: '1px solid',
        borderColor: (t) => alpha(t.palette.divider, 0.9),
        background: (t) =>
          `linear-gradient(165deg, ${alpha(t.palette.primary.main, 0.04)} 0%, ${alpha(t.palette.background.paper, 1)} 42%)`,
        boxShadow: (t) => `0 1px 0 ${alpha(t.palette.common.black, 0.04)}`,
      }}
    >
      <Stack spacing={2}>
        {/* Header row */}
        <Stack direction="row" justifyContent="space-between" alignItems="flex-start" flexWrap="wrap" useFlexGap>
          <Box sx={{ minWidth: 200, flex: 1 }}>
            <Typography variant="overline" color="text.secondary" sx={{ letterSpacing: 0.12, fontWeight: 600 }}>
              DSI Validation
            </Typography>
            <Typography variant="h6" sx={{ fontWeight: 600, mt: 0.25 }}>
              {phaseLabel}
            </Typography>
            {phaseDescription ? (
              <Typography variant="body2" color="text.secondary" sx={{ mt: 0.5, maxWidth: 640 }}>
                {phaseDescription}
              </Typography>
            ) : null}
          </Box>
          <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap" useFlexGap sx={{ pt: 0.5 }}>
            {isRunning ? (
              <Chip
                size="small"
                label="In progress"
                color="primary"
                variant="outlined"
                sx={{ animation: `${pulse} 1.6s ease-in-out infinite` }}
              />
            ) : null}
            {elapsedSec != null ? (
              <Typography variant="caption" color="text.secondary">
                Elapsed {formatElapsed(elapsedSec)}
              </Typography>
            ) : null}
            {queueWaitLabel ? (
              <Typography variant="caption" color="text.secondary">
                {queueWaitLabel}
              </Typography>
            ) : null}
          </Stack>
        </Stack>

        {/* Progress bar */}
        <LinearProgress
          variant={hasDeterminate ? 'determinate' : 'indeterminate'}
          value={hasDeterminate ? Math.min(100, pct) : undefined}
          sx={{
            height: 4,
            borderRadius: 99,
            bgcolor: (t) => alpha(t.palette.primary.main, 0.12),
            '& .MuiLinearProgress-bar': { borderRadius: 99 },
          }}
        />

        {/* Phase rail */}
        <Stack direction="row" spacing={0.5} flexWrap="wrap" useFlexGap sx={{ pt: 0.25 }}>
          {DSI_PROGRESS_PHASES.map((p, i) => {
            const isLast = i === DSI_PROGRESS_PHASES.length - 1;
            const idx = PHASE_ORDER.indexOf(p.id);
            const state: 'complete' | 'current' | 'waiting' | 'failed' =
              rawPhase === 'failed'
                ? 'failed'
                : idx < currentPhaseIndex
                  ? 'complete'
                  : idx === currentPhaseIndex
                    ? 'current'
                    : 'waiting';
            const color =
              state === 'complete'
                ? 'success.main'
                : state === 'failed'
                  ? 'error.main'
                  : state === 'current'
                    ? 'primary.main'
                    : 'text.disabled';
            const bg =
              state === 'complete'
                ? 'success.main'
                : state === 'failed'
                  ? 'error.main'
                  : state === 'current'
                    ? 'primary.main'
                    : 'action.hover';
            return (
              <Stack
                key={p.id}
                direction="row"
                alignItems="center"
                sx={{ flex: isLast ? '0 0 auto' : '1 1 0', minWidth: 0 }}
              >
                <Stack alignItems="center" sx={{ flex: 1, minWidth: 0 }}>
                  <Box
                    sx={{
                      width: 10,
                      height: 10,
                      borderRadius: '50%',
                      bgcolor: bg,
                      opacity: state === 'waiting' ? 0.35 : 1,
                      boxShadow:
                        state === 'current'
                          ? (t) => `0 0 0 4px ${alpha(t.palette.primary.main, 0.2)}`
                          : 'none',
                      transition: 'box-shadow 0.25s ease, opacity 0.25s ease',
                    }}
                  />
                  <Typography
                    variant="caption"
                    sx={{
                      mt: 0.5,
                      fontSize: 10,
                      fontWeight: state === 'current' ? 600 : 500,
                      color,
                      textAlign: 'center',
                    }}
                  >
                    {p.label}
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
                      bgcolor: (t) =>
                        alpha(t.palette.text.primary, idx < currentPhaseIndex ? 0.18 : 0.08),
                      minWidth: 8,
                    }}
                  />
                ) : null}
              </Stack>
            );
          })}
        </Stack>

        {/* Row count details — only show when we have data */}
        {totalRows > 0 ? (
          <Accordion
            disableGutters
            elevation={0}
            sx={{ bgcolor: 'transparent', '&:before': { display: 'none' } }}
          >
            <AccordionSummary expandIcon={<ExpandMoreIcon fontSize="small" />}>
              <Typography variant="caption" color="text.secondary" fontWeight={600}>
                Row progress &amp; details
              </Typography>
            </AccordionSummary>
            <AccordionDetails>
              <Stack spacing={0.75}>
                <Typography variant="body2" color="text.secondary">
                  <strong>Rows in file:</strong> {formatNum(totalRows)}
                </Typography>
                {currentRow > 0 ? (
                  <Typography variant="body2" color="text.secondary">
                    <strong>Rows processed:</strong> {formatNum(currentRow)} ({pct}%)
                  </Typography>
                ) : null}
                <Typography variant="caption" color="text.secondary" component="div">
                  Stage: {progress?.stage ?? '—'} · Task state: {progress?.task_state ?? '—'}
                </Typography>
              </Stack>
            </AccordionDetails>
          </Accordion>
        ) : null}
      </Stack>
    </Box>
  );
}
