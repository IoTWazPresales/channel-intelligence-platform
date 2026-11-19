'use client';

import { Alert, Button, Stack, Typography } from '@mui/material';
import { useMutation, useQueryClient } from '@tanstack/react-query';

import { formatUnits, type LineupPlanRow } from '@/features/lineup/lineupTypes';
import { groupLineupRows, type LineupGroup, type LineupSlice } from '@/features/lineup/lineupViews';
import { apiPost, safeDisplayError } from '@/lib/api';

type Props = {
  rows: LineupPlanRow[];
  slice: LineupSlice | null;
  onOpen: (group: LineupGroup) => void;
};

/** Final wave (b): the master line-up grouped by customer and period, decided at line-up level. */
export function LineupGroupsPanel({ rows, slice, onOpen }: Props) {
  const qc = useQueryClient();
  const decide = useMutation({
    mutationFn: (v: { group: LineupGroup; status: 'approved' | 'rejected' }) =>
      apiPost('/api/v1/lineup/items/group-approval', {
        customer_id: v.group.customerId,
        period_start: v.group.periodStart,
        approval_status: v.status,
        only_pending: true,
      }),
    onSuccess: () => void qc.invalidateQueries({ queryKey: ['lineup-items'] }),
  });
  const groups = groupLineupRows(rows);
  if (!groups.length) return null;
  return (
    <Stack spacing={0.75} data-testid="lineup-groups" sx={{ px: 1 }}>
      <Typography variant="subtitle2">Line-ups by customer and period</Typography>
      {decide.isError ? <Alert severity="error">{safeDisplayError(decide.error)}</Alert> : null}
      {groups.map((g) => {
        const active = slice?.customerId === g.customerId && slice?.periodStart === g.periodStart;
        return (
          <Stack
            key={g.key}
            direction="row"
            spacing={1}
            alignItems="center"
            flexWrap="wrap"
            useFlexGap
            data-testid={`lineup-group-${g.key}`}
            sx={{ fontWeight: active ? 600 : undefined }}
          >
            <Typography variant="body2" sx={{ minWidth: 160, fontWeight: 600 }}>
              {g.customerName}
            </Typography>
            <Typography variant="body2" sx={{ minWidth: 90 }}>
              {g.periodLabel}
            </Typography>
            <Typography
              variant="body2"
              color="text.secondary"
              sx={{ flex: 1, minWidth: 220 }}
              data-testid={`lineup-group-counts-${g.key}`}
            >
              {g.lines} lines · {formatUnits(g.plannedUnits)} units · {g.pending} pending ·{' '}
              {g.approved} approved · {g.rejected} rejected
            </Typography>
            <Button
              size="small"
              variant={active ? 'contained' : 'text'}
              data-testid={`lineup-group-open-${g.key}`}
              onClick={() => onOpen(g)}
            >
              {active ? 'Viewing' : 'Open'}
            </Button>
            <Button
              size="small"
              variant="outlined"
              color="success"
              disabled={decide.isPending || g.pending === 0}
              data-testid={`lineup-group-approve-${g.key}`}
              onClick={() => decide.mutate({ group: g, status: 'approved' })}
            >
              Approve line-up
            </Button>
            <Button
              size="small"
              variant="outlined"
              color="error"
              disabled={decide.isPending || g.pending === 0}
              data-testid={`lineup-group-reject-${g.key}`}
              onClick={() => decide.mutate({ group: g, status: 'rejected' })}
            >
              Reject line-up
            </Button>
          </Stack>
        );
      })}
    </Stack>
  );
}
