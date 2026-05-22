'use client';

import CloseIcon from '@mui/icons-material/Close';
import SyncIcon from '@mui/icons-material/Sync';
import {
  Badge,
  Box,
  IconButton,
  LinearProgress,
  Menu,
  MenuItem,
  Stack,
  Tooltip,
  Typography,
} from '@mui/material';
import Link from 'next/link';
import { useState } from 'react';

import { useGlobalBackgroundTasks } from './useGlobalBackgroundTasks';
import type { BackgroundTaskRecord } from './importJobProgress.types';

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

export function GlobalBackgroundTasksIndicator() {
  const { tasks, activeCount, dismissTask } = useGlobalBackgroundTasks();
  const [anchor, setAnchor] = useState<null | HTMLElement>(null);
  const open = Boolean(anchor);

  if (tasks.length === 0) return null;

  return (
    <>
      <Tooltip title={activeCount > 0 ? `${activeCount} background task(s) running` : 'Recent background tasks'}>
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
        slotProps={{ paper: { sx: { width: 360, maxWidth: '95vw' } } }}
        data-testid="global-background-tasks-menu"
      >
        <Box sx={{ px: 2, py: 1 }}>
          <Typography variant="subtitle2">Background tasks</Typography>
        </Box>
        {tasks.map((task) => (
          <MenuItem
            key={task.task_id}
            component={Link}
            href={taskHref(task)}
            onClick={() => setAnchor(null)}
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
                  aria-label="Dismiss"
                  onClick={(e) => {
                    e.preventDefault();
                    e.stopPropagation();
                    dismissTask(task.task_id);
                  }}
                  sx={{ ml: 0.5, mt: -0.5 }}
                >
                  <CloseIcon fontSize="small" />
                </IconButton>
              </Stack>
              <Typography variant="caption" color="text.secondary">
                {task.phase_label ?? 'Running'}
              </Typography>
              <TaskProgress task={task} />
            </Stack>
          </MenuItem>
        ))}
      </Menu>
    </>
  );
}
