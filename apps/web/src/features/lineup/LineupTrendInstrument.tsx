'use client';

import { Box, Typography } from '@mui/material';
import { alpha, useTheme } from '@mui/material/styles';

const Q1_BARS = [
  { plan: 100, ship: 78 },
  { plan: 88, ship: 70 },
  { plan: 92, ship: 76 },
];
const Q2_BARS = [
  { plan: 95, ship: 58 },
  { plan: 100, ship: 62 },
  { plan: 86, ship: 54 },
];

function BarPair({ plan, ship }: { plan: number; ship: number }) {
  return (
    <Box sx={{ flex: 1, display: 'flex', alignItems: 'flex-end', gap: '2px', height: '100%' }}>
      <Box sx={{ flex: 1, height: `${plan}%`, bgcolor: alpha('#78a0be', 0.22), borderRadius: '1px 1px 0 0' }} />
      <Box sx={{ flex: 1, height: `${ship}%`, bgcolor: '#3db8e8', opacity: 0.78, borderRadius: '1px 1px 0 0' }} />
    </Box>
  );
}

export function LineupTrendInstrument() {
  const theme = useTheme();

  return (
    <Box data-testid="lineup-trend-instrument">
      <Box sx={{ display: 'flex', justifyContent: 'space-between', mb: 1 }}>
        <Typography sx={{ fontSize: '9.5px', letterSpacing: '0.08em', textTransform: 'uppercase', color: alpha(theme.palette.text.primary, 0.45) }}>
          Planned vs shipped by period
        </Typography>
        <Typography sx={{ fontFamily: '"IBM Plex Mono", monospace', fontSize: '10px', color: alpha(theme.palette.text.primary, 0.45) }}>
          plan · shipped
        </Typography>
      </Box>
      <Box sx={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 2.5 }}>
        {[
          { label: 'Q1 · Jan–Mar', bars: Q1_BARS },
          { label: 'Q2 · Apr–Jun', bars: Q2_BARS },
        ].map((period) => (
          <Box key={period.label} sx={{ borderTop: `1px dashed ${alpha(theme.palette.text.primary, 0.28)}`, pt: 1 }}>
            <Typography sx={{ fontSize: '9.5px', letterSpacing: '0.08em', textTransform: 'uppercase', color: alpha(theme.palette.text.primary, 0.45), mb: 1 }}>
              {period.label}
            </Typography>
            <Box sx={{ display: 'flex', alignItems: 'flex-end', gap: 0.75, height: 64 }}>
              {period.bars.map((b, i) => (
                <BarPair key={i} plan={b.plan} ship={b.ship} />
              ))}
            </Box>
          </Box>
        ))}
      </Box>
    </Box>
  );
}
