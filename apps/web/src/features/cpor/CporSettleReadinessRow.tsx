'use client';

import { Box, Typography } from '@mui/material';

import {
  buildSettleReadinessChips,
  type SettleReadiness,
} from '@/features/cpor/fxDisplay';

const toneSx = {
  pass: {
    color: '#9dceb4',
    bgcolor: 'rgba(61,155,106,.13)',
    borderColor: 'rgba(61,155,106,.35)',
  },
  open: {
    color: '#e8d4a8',
    bgcolor: 'rgba(212,161,90,.13)',
    borderColor: 'rgba(212,161,90,.35)',
  },
  fail: {
    color: '#e8b4b4',
    bgcolor: 'rgba(196,92,92,.14)',
    borderColor: 'rgba(196,92,92,.4)',
  },
} as const;

export function CporSettleReadinessRow({
  readiness,
  testIdPrefix = 'cpor-readiness',
}: {
  readiness: SettleReadiness;
  testIdPrefix?: string;
}) {
  const chips = buildSettleReadinessChips(readiness);

  return (
    <Box
      sx={{ display: 'flex', flexWrap: 'wrap', gap: 1, alignItems: 'center' }}
      data-testid={`${testIdPrefix}-row`}
    >
      <Typography
        component="span"
        sx={{
          fontSize: '9.5px',
          letterSpacing: '0.09em',
          textTransform: 'uppercase',
          color: 'text.disabled',
          mr: 0.5,
        }}
      >
        Readiness
      </Typography>
      {chips.map((chip) => (
        <Box
          key={chip.key}
          component="span"
          data-testid={`${testIdPrefix}-${chip.key}`}
          data-tone={chip.tone}
          sx={{
            fontSize: '11.5px',
            px: 1.25,
            py: 0.75,
            borderRadius: '4px',
            border: '1px solid',
            fontFamily: 'var(--font-mono, "IBM Plex Mono", ui-monospace, monospace)',
            ...toneSx[chip.tone],
          }}
        >
          {chip.tone === 'pass' && chip.key === 'fx' ? `✓ ${chip.label}` : chip.label}
        </Box>
      ))}
    </Box>
  );
}
