'use client';

import { Box, Typography } from '@mui/material';
import { useTheme } from '@mui/material/styles';

import { tokensFor } from '@/theme/cipTokens';

/** Filled dot: a pin a steward saved. Hollow dashed dot: a proposal still waiting for a steward. */
export function PinLegend() {
  const theme = useTheme();
  const tokens = tokensFor(theme.palette.mode);
  const dot = { width: 12, height: 12, borderRadius: '50%', flexShrink: 0 } as const;
  return (
    <Box data-testid="store-pin-legend" sx={{ display: 'flex', gap: 1.5, flexWrap: 'wrap', alignItems: 'center', mb: 1 }}>
      <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
        <Box data-testid="legend-confirmed-dot" sx={{ ...dot, bgcolor: tokens.semantic.success, border: `2px solid ${tokens.bg.surface}` }} />
        <Typography variant="caption" sx={{ color: tokens.text.secondary }}>Confirmed pin</Typography>
      </Box>
      <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
        <Box data-testid="legend-proposed-dot" sx={{ ...dot, bgcolor: 'transparent', border: `2px dashed ${tokens.text.primary}` }} />
        <Typography variant="caption" sx={{ color: tokens.text.secondary }}>Proposed pin, not saved until you confirm</Typography>
      </Box>
    </Box>
  );
}
