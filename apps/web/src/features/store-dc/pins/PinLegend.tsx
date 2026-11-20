'use client';

import { Box, Typography } from '@mui/material';
import { useTheme } from '@mui/material/styles';

import { MarkerDot } from '@/features/maps/MapMarker';
import { tokensFor } from '@/theme/cipTokens';

/** Solid marker: a pin a steward saved. Hollow dashed marker: a proposal still waiting for a steward. */
export function PinLegend() {
  const theme = useTheme();
  const tokens = tokensFor(theme.palette.mode);
  return (
    <Box data-testid="store-pin-legend" sx={{ display: 'flex', gap: 1.5, flexWrap: 'wrap', alignItems: 'center', mb: 1 }}>
      <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
        <MarkerDot data-testid="legend-confirmed-dot" color={tokens.semantic.success} glow={false} />
        <Typography variant="caption" sx={{ color: tokens.text.secondary }}>Confirmed pin</Typography>
      </Box>
      <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
        <MarkerDot data-testid="legend-proposed-dot" color={tokens.text.primary} hollow glow={false} />
        <Typography variant="caption" sx={{ color: tokens.text.secondary }}>Proposed pin, not saved until you confirm</Typography>
      </Box>
    </Box>
  );
}
