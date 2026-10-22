'use client';

import TerminalIcon from '@mui/icons-material/Terminal';
import { Button } from '@mui/material';

import { roleMayAccess } from '@/features/shell/navConfig';
import { useCurrentUser } from '@/features/shell/useCurrentUser';

import { useLogDrawerStore } from './logDrawerStore';

/** "Show this job's log": opens the live log drawer filtered to one import job. Administrators only; nothing for anyone else. */
export function ShowJobLogButton({ jobId }: { jobId: number }) {
  const { data: me } = useCurrentUser();
  const openLogs = useLogDrawerStore((s) => s.openLogs);
  if (!roleMayAccess(me?.role ? String(me.role) : null, ['admin'])) return null;
  return (
    <Button
      size="small"
      variant="outlined"
      startIcon={<TerminalIcon />}
      onClick={() => openLogs({ jobId })}
      data-testid="show-job-log"
    >
      Show this job&apos;s log
    </Button>
  );
}
