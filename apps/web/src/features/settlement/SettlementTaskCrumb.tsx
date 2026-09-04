'use client';

import { Box, Typography } from '@mui/material';
import { alpha, useTheme } from '@mui/material/styles';

export function SettlementTaskCrumb() {
  const theme = useTheme();
  return (
    <Box data-testid="settlement-task-crumb" sx={{ display: 'flex', alignItems: 'baseline', gap: 1 }}>
      <Typography sx={{ fontSize: '11px', letterSpacing: '0.08em', textTransform: 'uppercase', color: alpha(theme.palette.text.primary, 0.45) }}>
        Promotions &amp; Funding
      </Typography>
      <Typography sx={{ color: alpha(theme.palette.text.primary, 0.25) }}>/</Typography>
      <Typography sx={{ fontSize: '11px', letterSpacing: '0.08em', textTransform: 'uppercase', color: alpha(theme.palette.text.primary, 0.72) }}>
        Case book
      </Typography>
    </Box>
  );
}
