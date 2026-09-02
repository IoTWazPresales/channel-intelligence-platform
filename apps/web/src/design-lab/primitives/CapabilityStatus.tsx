'use client';

import { Chip, Tooltip } from '@mui/material';

import { leafStatusLabel, type LeafStatus } from '../shell/labNav';

/**
 * Four-state capability marker (CONSULT Q4). One vocabulary everywhere — rail, directory, domain
 * overview, surfaces — so an operator never has to guess whether a screen is real, partly real,
 * data-only or planned. `live` renders nothing: absence of a marker means it works.
 */
const tone: Record<LeafStatus, { color: 'default' | 'warning' | 'info'; hint: string }> = {
  live: { color: 'default', hint: 'End-to-end usable on real data.' },
  partial: { color: 'warning', hint: 'Real code path, but a required step is missing, manual or hard-coded. Details on the surface.' },
  substrate: { color: 'info', hint: 'Tables or endpoints exist; there is no working user-facing view yet. Nothing here is computed for you.' },
  planned: { color: 'default', hint: 'Chartered on the roadmap, not built. Shown so you know where it will live.' },
};

export function CapabilityStatus({ status, size = 'small' }: { status?: LeafStatus; size?: 'small' | 'inline' }) {
  const s = status ?? 'live';
  if (s === 'live') return null;
  const t = tone[s];
  return (
    <Tooltip title={t.hint} arrow>
      <Chip
        data-testid={`capability-status-${s}`}
        size="small"
        color={t.color}
        variant={s === 'planned' ? 'outlined' : 'filled'}
        label={leafStatusLabel[s]}
        sx={{ height: size === 'inline' ? 18 : 20, fontSize: 10.5, fontWeight: 600, letterSpacing: 0.2, '& .MuiChip-label': { px: 0.75 }, ...(s === 'planned' ? { color: 'text.disabled', borderStyle: 'dashed' } : {}) }}
      />
    </Tooltip>
  );
}
