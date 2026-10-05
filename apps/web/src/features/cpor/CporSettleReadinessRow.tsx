'use client';

import { Box, Typography } from '@mui/material';
import { alpha, useTheme } from '@mui/material/styles';

import {
  buildSettleReadinessChips,
  type SettleReadiness,
} from '@/features/cpor/fxDisplay';

function toneSx(theme: { palette: { success: { main: string }; warning: { main: string }; error: { main: string } } }) {
  const chip = (color: string) => ({
    color,
    bgcolor: alpha(color, 0.12),
    borderColor: alpha(color, 0.35),
  });
  return {
    pass: chip(theme.palette.success.main),
    open: chip(theme.palette.warning.main),
    fail: chip(theme.palette.error.main),
  };
}

export function CporSettleReadinessRow({
  readiness,
  testIdPrefix = 'cpor-readiness',
}: {
  readiness: SettleReadiness;
  testIdPrefix?: string;
}) {
  const chips = buildSettleReadinessChips(readiness);
  const tones = toneSx(useTheme());

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
            ...tones[chip.tone],
          }}
        >
          {chip.tone === 'pass' && chip.key === 'fx' ? `✓ ${chip.label}` : chip.label}
        </Box>
      ))}
    </Box>
  );
}
