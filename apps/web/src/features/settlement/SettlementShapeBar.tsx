'use client';

import { Box } from '@mui/material';
import { alpha, useTheme } from '@mui/material/styles';

type Props = {
  settledPct: number;
  outstandingPct: number;
  blockedPct: number;
  height?: number;
};

export function SettlementShapeBar({ settledPct, outstandingPct, blockedPct, height = 8 }: Props) {
  const theme = useTheme();
  const total = Math.max(settledPct + outstandingPct + blockedPct, 0.001);
  const settledW = (settledPct / total) * 100;
  const outstandingW = (outstandingPct / total) * 100;
  const blockedW = (blockedPct / total) * 100;

  return (
    <Box
      data-testid="settlement-shape-bar"
      sx={{
        display: 'flex',
        width: '100%',
        height,
        borderRadius: 0.5,
        overflow: 'hidden',
        bgcolor: alpha(theme.palette.common.white, 0.06),
      }}
    >
      {settledW > 0 ? (
        <Box sx={{ width: `${settledW}%`, bgcolor: alpha(theme.palette.success.main, 0.65) }} />
      ) : null}
      {outstandingW > 0 ? (
        <Box sx={{ width: `${outstandingW}%`, bgcolor: alpha(theme.palette.info.main, 0.55) }} />
      ) : null}
      {blockedW > 0 ? (
        <Box
          sx={{
            width: `${blockedW}%`,
            background: `repeating-linear-gradient(45deg, ${alpha(theme.palette.warning.main, 0.5)}, ${alpha(theme.palette.warning.main, 0.5)} 4px, transparent 4px, transparent 8px)`,
          }}
        />
      ) : null}
    </Box>
  );
}
