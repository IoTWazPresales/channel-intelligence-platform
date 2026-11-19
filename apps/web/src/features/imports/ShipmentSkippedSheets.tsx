'use client';

import { Chip, Stack, Typography } from '@mui/material';

export type SkippedSheet = { sheet: string; reason: string };

const REASON_LABEL: Record<string, string> = {
  not_selected: 'not selected',
  unrecognised_layout: 'layout not recognised',
};

/** BACKLOG-046: sheets this import leaves out, so their columns are not in the mapping step. */
export function ShipmentSkippedSheets({ sheets }: { sheets: SkippedSheet[] | undefined | null }) {
  const list = (sheets ?? []).filter((s) => s && s.sheet);
  if (!list.length) return null;
  return (
    <Stack spacing={0.5} data-testid="shipment-skipped-sheets">
      <Typography variant="body2" color="text.secondary">
        Not imported (their columns are not in the mapping below):
      </Typography>
      <Stack direction="row" spacing={1} useFlexGap flexWrap="wrap">
        {list.map((s) => (
          <Chip
            key={`${s.sheet}:${s.reason}`}
            size="small"
            variant="outlined"
            label={`${s.sheet} · Ignored, ${REASON_LABEL[s.reason] ?? s.reason}`}
            data-testid="shipment-skipped-sheet"
          />
        ))}
      </Stack>
    </Stack>
  );
}