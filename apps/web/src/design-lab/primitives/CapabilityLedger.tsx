'use client';

import { Box, Stack, Typography } from '@mui/material';

import type { Capability } from '../fixtures/commercial';
import { CapabilityStatus } from './CapabilityStatus';
import { Panel } from './Panel';

/**
 * "What works here" — the per-surface truth table. Every commercial surface carries one so the
 * operator can see, on the screen itself, which jobs are live, partly built, data-only or planned.
 * This is how the prototype avoids visually pretending that unbuilt capability already works.
 */
export function CapabilityLedger({ items, title = 'What works here', subtitle }: { items: Capability[]; title?: string; subtitle?: string }) {
  return (
    <Panel title={title} subtitle={subtitle ?? 'Status per job on this surface — unmarked rows work today'} flush>
      <Stack component="ul" spacing={0} sx={{ listStyle: 'none', m: 0, p: 0, pb: 0.5 }} data-testid="capability-ledger">
        {items.map((c) => (
          <Box component="li" key={c.label} sx={{ px: 2, py: 0.85, borderTop: '1px solid', borderColor: 'divider', display: 'grid', gridTemplateColumns: 'minmax(0, 1fr) auto', columnGap: 1.5, rowGap: 0.25 }}>
            <Typography variant="body2" sx={{ fontWeight: 500, color: c.state === 'planned' ? 'text.disabled' : 'text.primary' }}>
              {c.label}
            </Typography>
            <Box sx={{ justifySelf: 'end' }}>
              <CapabilityStatus status={c.state} size="inline" />
            </Box>
            <Typography variant="caption" color="text.secondary" sx={{ gridColumn: '1 / -1' }}>
              {c.note}
            </Typography>
          </Box>
        ))}
      </Stack>
    </Panel>
  );
}
