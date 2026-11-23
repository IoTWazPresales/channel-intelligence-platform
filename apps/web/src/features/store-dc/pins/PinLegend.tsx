'use client';

import { Box, Typography } from '@mui/material';
import { useTheme } from '@mui/material/styles';

import { MarkerDot } from '@/features/maps/MapMarker';
import { tokensFor } from '@/theme/cipTokens';

/** Solid marker: a pin a steward saved. Filled dot with dashed outer ring: a proposal waiting for a steward. */
export function PinLegend() {
  const theme = useTheme();
  const tokens = tokensFor(theme.palette.mode);
  return (
    <Box data-testid="store-pin-legend" sx={{ display: 'flex', gap: 1.5, flexWrap: 'wrap', alignItems: 'center' }}>
      <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.75 }}>
        <MarkerDot data-testid="legend-confirmed-dot" color={tokens.semantic.success} glow={false} />
        <Typography variant="caption" sx={{ color: tokens.text.secondary }}>Confirmed pin</Typography>
      </Box>
      <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.75 }}>
        <MarkerDot data-testid="legend-proposed-dot" color={tokens.text.primary} proposed glow={false} />
        <Typography variant="caption" sx={{ color: tokens.text.secondary }}>Proposed pin, not saved until you confirm</Typography>
      </Box>
    </Box>
  );
}

export function StoreMapPanelHeader() {
  const theme = useTheme();
  const tokens = tokensFor(theme.palette.mode);
  return (
    <Box
      data-testid="store-map-panel-header"
      sx={{ display: 'flex', flexWrap: 'wrap', gap: 1.5, alignItems: 'center', justifyContent: 'space-between', px: 0.5 }}
    >
      <PinLegend />
      <Box data-testid="store-map-legend" sx={{ display: 'flex', alignItems: 'center', gap: 1, minWidth: 180 }}>
        <Typography variant="caption" sx={{ color: tokens.text.secondary }}>Worst</Typography>
        <Box sx={{
          flex: 1, height: 8, borderRadius: 4,
          background: `linear-gradient(90deg, ${tokens.semantic.danger}, ${tokens.semantic.success})`,
        }} />
        <Typography variant="caption" sx={{ color: tokens.text.secondary }}>Best</Typography>
      </Box>
    </Box>
  );
}
