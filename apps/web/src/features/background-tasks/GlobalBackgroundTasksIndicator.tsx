'use client';

import CloseIcon from '@mui/icons-material/Close';
import SyncIcon from '@mui/icons-material/Sync';
import {
  Alert,
  Badge,
  Box,
  Button,
  IconButton,
  LinearProgress,
  Menu,
  MenuItem,
  Snackbar,
  Stack,
  Tooltip,
  Typography,
} from '@mui/material';
import Link from 'next/link';
import { useCallback, useEffect, useRef, useState, type MouseEvent } from 'react';

import { useGlobalBackgroundTasks } from './useGlobalBackgroundTasks';
import type { BackgroundTaskRecord } from './importJobProgress.types';

const UNDO_MS = 5000;

function formatRows(current: number, total: number): string {
  if (total > 0) return `${current.toLocaleString()} / ${total.toLocaleString()} rows`;
  if (current > 0) return `${current.toLocaleString()} rows`;
  return '';
}

function TaskProgress({ task }: { task: BackgroundTaskRecord }) {
  const total = task.total_rows ?? 0;
  const pct = task.pct ?? 0;
  const determinate = total > 0 && pct > 0 && task.status === 'running';
  return (
    <Box sx={{ width: '100%', mt: 0.75 }}>
      <LinearProgress
        variant={determinate ? 'determinate' : 'indeterminate'}
        value={determinate ? Math.min(100, pct) : undefined}
        color={task.status === 'failed' ? 'error' : 'primary'}
        sx={{ height: 4, borderRadius: 99 }}
      />
      {formatRows(task.current_row ?? 0, total) ? (
        <Typography variant="caption" color="text.secondary" sx={{ mt: 0.5, display: 'block' }}>
          {formatRows(task.current_row ?? 0, total)}
          {determinate ? ` (${pct}%)` : ''}
        </Typography>
      ) : null}
    </Box>
  );
}

function taskHref(task: BackgroundTaskRecord): string {
  if (task.template_slug === 'inbound_shipments') {
    return `/admin/imports?job_id=${task.import_job_id}`;
  }
  if (task.template_slug === 'distributor_inventory') {
    return `/admin/mappings?import_job_id=${task.import_job_id}`;
  }
  return `/admin/imports?job_id=${task.import_job_id}`;
}

type UndoToast = {
  jobId: number;
  open: boolean;
};

export function GlobalBackgroundTasksIndicator() {
  const { tasks, activeCount, dismissTask, cancelTask, retryTask, isCancelling, retryMutation } =
    useGlobalBackgroundTasks();
  const [anchor, setAnchor] = useState<null | HTMLElement>(null);
  const [undoToast, setUndoToast] = useState<UndoToast | null>(null);
  const undoTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const open = Boolean(anchor);

  const clearUndoTimer = useCallback(() => {
    if (undoTimerRef.current != null) {
      clearTimeout(undoTimerRef.current);
      undoTimerRef.current = null;
    }
  }, []);

  useEffect(() => () => clearUndoTimer(), [clearUndoTimer]);

  const handleCloseTask = useCallback(
    async (task: BackgroundTaskRecord, e: MouseEvent) => {
      e.preventDefault();
      e.stopPropagation();
      if (task.status === 'failed') {
        dismissTask(task);
        return;
      }
      if (task.status !== 'running') {
        dismissTask(task);
        return;
      }
      try {
        await cancelTask(task);
        clearUndoTimer();
        setUndoToast({ jobId: task.import_job_id, open: true });
        undoTimerRef.current = setTimeout(() => {
          setUndoToast(null);
          undoTimerRef.current = null;
        }, UNDO_MS);
      } catch {
        /* error surfaced via query invalidation / job status */
      }
    },
    [cancelTask, dismissTask, clearUndoTimer]
  );

  const handleUndo = useCallback(async () => {
    if (!undoToast) return;
    clearUndoTimer();
    const jobId = undoToast.jobId;
    setUndoToast(null);
    try {
      await retryTask({ task_id: `failed-job-${jobId}`, import_job_id: jobId, kind: 'dsi_pipeline', label: '', status: 'failed' });
    } catch {
      /* job may no longer be failed */
    }
  }, [undoToast, clearUndoTimer, retryTask]);

  if (tasks.length === 0 && !undoToast?.open) return null;

  return (
    <>
      <Tooltip title={activeCount > 0 ? `${activeCount} background task(s) running` : 'Background tasks'}>
        <IconButton
          color="inherit"
          aria-label="Background tasks"
          onClick={(e) => setAnchor(e.currentTarget)}
          data-testid="global-background-tasks-trigger"
        >
          <Badge badgeContent={activeCount > 0 ? activeCount : undefined} color="primary">
            <SyncIcon
              sx={
                activeCount > 0
                  ? { animation: 'spin 1.2s linear infinite', '@keyframes spin': { to: { transform: 'rotate(360deg)' } } }
                  : undefined
              }
            />
          </Badge>
        </IconButton>
      </Tooltip>
      <Menu
        anchorEl={anchor}
        open={open}
        onClose={() => setAnchor(null)}
        slotProps={{ paper: { sx: { width: 380, maxWidth: '95vw' } } }}
        data-testid="global-background-tasks-menu"
      >
        <Box sx={{ px: 2, py: 1 }}>
          <Typography variant="subtitle2">Background tasks</Typography>
        </Box>
        {tasks.map((task) => {
          const cancelling = isCancelling(task.import_job_id);
          const isRunning = task.status === 'running';
          const isFailed = task.status === 'failed';
          const closeLabel = isRunning ? 'Cancel task' : 'Dismiss';
          return (
            <MenuItem
              key={task.task_id}
              component={isFailed ? 'div' : Link}
              href={isFailed ? undefined : taskHref(task)}
              onClick={isFailed ? undefined : () => setAnchor(null)}
              sx={{ alignItems: 'flex-start', whiteSpace: 'normal', py: 1.25 }}
              data-testid={`background-task-${task.task_id}`}
            >
              <Stack spacing={0.25} sx={{ width: '100%', pr: 3 }}>
                <Stack direction="row" justifyContent="space-between" alignItems="flex-start">
                  <Typography variant="body2" fontWeight={600}>
                    {task.label}
                  </Typography>
                  <IconButton
                    size="small"
                    aria-label={closeLabel}
                    onClick={(e) => void handleCloseTask(task, e)}
                    disabled={cancelling}
                    sx={{ ml: 0.5, mt: -0.5 }}
                    data-testid={`background-task-close-${task.import_job_id}`}
                  >
                    <CloseIcon fontSize="small" />
                  </IconButton>
                </Stack>
                <Typography variant="caption" color={isFailed ? 'error' : 'text.secondary'}>
                  {cancelling
                    ? 'Cancelling…'
                    : isFailed
                      ? 'Failed'
                      : (task.phase_label ?? 'Running')}
                </Typography>
                {isFailed ? (
                  <Button
                    size="small"
                    variant="outlined"
                    color="error"
                    sx={{ mt: 0.5, alignSelf: 'flex-start' }}
                    disabled={retryMutation.isPending}
                    onClick={(e) => {
                      e.preventDefault();
                      e.stopPropagation();
                      void retryTask(task);
                    }}
                    data-testid={`background-task-retry-${task.import_job_id}`}
                  >
                    Retry
                  </Button>
                ) : isRunning ? (
                  <TaskProgress task={task} />
                ) : null}
              </Stack>
            </MenuItem>
          );
        })}
      </Menu>
      <Snackbar
        open={Boolean(undoToast?.open)}
        autoHideDuration={UNDO_MS}
        onClose={() => {
          clearUndoTimer();
          setUndoToast(null);
        }}
        anchorOrigin={{ vertical: 'bottom', horizontal: 'center' }}
      >
        <Alert
          severity="info"
          sx={{ width: '100%', alignItems: 'center' }}
          action={
            <Button color="inherit" size="small" onClick={() => void handleUndo()} data-testid="background-task-undo">
              Undo
            </Button>
          }
        >
          Cancelled — Undo
        </Alert>
      </Snackbar>
    </>
  );
}
