'use client';

import { Box } from '@mui/material';
import { useTheme } from '@mui/material/styles';

import { tokensFor } from '@/theme/cipTokens';

type MapViewControlsProps = {
  onZoomIn: () => void;
  onZoomOut: () => void;
  onReset: () => void;
  canZoomIn: boolean;
  canZoomOut: boolean;
  /** Reset only means something once the view has moved. */
  canReset: boolean;
  'data-testid'?: string;
};

/** Zoom and reset for a pannable map. Sits on the canvas and never starts a pan. */
export function MapViewControls({
  onZoomIn,
  onZoomOut,
  onReset,
  canZoomIn,
  canZoomOut,
  canReset,
  'data-testid': testId,
}: MapViewControlsProps) {
  const t = tokensFor(useTheme().palette.mode);
  const button = {
    minWidth: 28,
    height: 28,
    px: 1,
    font: 'inherit',
    fontSize: 12,
    fontWeight: 600,
    color: t.text.primary,
    bgcolor: t.bg.elevated,
    border: `1px solid ${t.border.strong}`,
    borderRadius: 1,
    cursor: 'pointer',
    '&:disabled': { cursor: 'default', opacity: 0.45 },
  } as const;
  return (
    <Box
      data-no-pan
      data-testid={testId}
      sx={{ position: 'absolute', top: 8, right: 8, zIndex: 3, display: 'flex', gap: 0.5 }}
    >
      <Box component="button" type="button" aria-label="Zoom in" data-testid="map-zoom-in" disabled={!canZoomIn} onClick={onZoomIn} sx={button}>
        +
      </Box>
      <Box component="button" type="button" aria-label="Zoom out" data-testid="map-zoom-out" disabled={!canZoomOut} onClick={onZoomOut} sx={button}>
        −
      </Box>
      <Box component="button" type="button" data-testid="map-reset-view" disabled={!canReset} onClick={onReset} sx={button}>
        Reset view
      </Box>
    </Box>
  );
}
