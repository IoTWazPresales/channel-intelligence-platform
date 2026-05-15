'use client';

import NotificationsNoneOutlinedIcon from '@mui/icons-material/NotificationsNoneOutlined';
import {
  Badge,
  Box,
  Button,
  Divider,
  IconButton,
  List,
  ListItem,
  ListItemText,
  Menu,
  Stack,
  Tooltip,
  Typography,
} from '@mui/material';
import { useCallback, useMemo, useState } from 'react';

import { useBackgroundTasks } from './BackgroundTasksProvider';

function formatTaskLine(t: Record<string, unknown>): string {
  const title = String(t.title ?? t.type ?? 'Task');
  const summary = String(t.summary ?? '').trim();
  if (summary) return `${title} — ${summary}`;
  const st = String(t.status ?? '');
  return `${title} (${st})`;
}

export function ActivityMenu() {
  const { tasks, redisAvailable, refresh, dismiss } = useBackgroundTasks();
  const [anchor, setAnchor] = useState<null | HTMLElement>(null);
  const open = Boolean(anchor);

  const running = useMemo(() => tasks.filter((t) => t.status === 'running' || t.status === 'queued'), [tasks]);
  const recent = useMemo(
    () => tasks.filter((t) => t.status === 'completed' || t.status === 'failed').slice(0, 12),
    [tasks]
  );

  const badge = running.length;

  const onDismiss = useCallback(
    async (id: string) => {
      await dismiss(id);
      setAnchor(null);
    },
    [dismiss]
  );

  return (
    <>
      <Tooltip title={redisAvailable ? 'Background activity' : 'Background activity (Redis offline — no live feed)'}>
        <IconButton color="inherit" aria-label="Background activity" onClick={(e) => setAnchor(e.currentTarget)}>
          <Badge badgeContent={badge} color="primary" overlap="circular" invisible={badge === 0}>
            <NotificationsNoneOutlinedIcon />
          </Badge>
        </IconButton>
      </Tooltip>
      <Menu anchorEl={anchor} open={open} onClose={() => setAnchor(null)} anchorOrigin={{ vertical: 'bottom', horizontal: 'right' }}>
        <Box sx={{ px: 2, py: 1, minWidth: 320, maxWidth: 440 }}>
          <Stack direction="row" justifyContent="space-between" alignItems="center">
            <Typography variant="subtitle2" fontWeight={600}>
              Activity
            </Typography>
            <Button size="small" onClick={() => refresh()}>
              Refresh
            </Button>
          </Stack>
          {!redisAvailable ? (
            <Typography variant="caption" color="warning.main" sx={{ display: 'block', mt: 0.5 }}>
              Redis is not reachable — background task progress is unavailable until Redis is configured.
            </Typography>
          ) : null}
        </Box>
        <Divider />
        <List dense sx={{ maxHeight: 360, py: 0 }}>
          {running.length === 0 && recent.length === 0 ? (
            <ListItem>
              <ListItemText primary="No active or recent tasks" secondary="PM commits and shipment re-resolution appear here." />
            </ListItem>
          ) : null}
          {running.map((t) => (
            <ListItem key={t.id}>
              <ListItemText primary={formatTaskLine(t)} secondary={String(t.status)} />
            </ListItem>
          ))}
          {recent.map((t) => (
            <ListItem
              key={t.id}
              secondaryAction={
                <Button size="small" onClick={() => onDismiss(t.id)}>
                  Dismiss
                </Button>
              }
            >
              <ListItemText primary={formatTaskLine(t)} secondary={String(t.status)} />
            </ListItem>
          ))}
        </List>
      </Menu>
    </>
  );
}
