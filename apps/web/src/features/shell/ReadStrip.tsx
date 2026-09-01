'use client';

import { Box, Typography } from '@mui/material';
import { alpha, useTheme } from '@mui/material/styles';

export function ReadStrip({ text }: { text: string }) {
  const theme = useTheme();
  const line = alpha(theme.palette.common.white, 0.12);

  const parts = text.split(/(\*\*[^*]+\*\*)/g).map((part, i) => {
    if (part.startsWith('**') && part.endsWith('**')) {
      return (
        <Box component="span" key={i} sx={{ color: theme.palette.text.primary, fontWeight: 600 }}>
          {part.slice(2, -2)}
        </Box>
      );
    }
    return part;
  });

  return (
    <Box
      data-testid="brief-read-strip"
      sx={{
        px: 2.75,
        py: 1.75,
        borderBottom: `1px solid ${line}`,
        bgcolor: '#1a1d23',
      }}
    >
      <Box sx={{ display: 'flex', alignItems: 'baseline', gap: 1.25 }}>
        <Typography
          component="span"
          sx={{
            fontFamily: '"IBM Plex Mono", monospace',
            fontSize: '9px',
            letterSpacing: '0.12em',
            textTransform: 'uppercase',
            color: '#3db8e8',
            border: '1px solid rgba(61,184,232,0.35)',
            borderRadius: '3px',
            px: 0.75,
            py: 0.25,
            flexShrink: 0,
          }}
        >
          Read
        </Typography>
        <Typography sx={{ m: 0, fontSize: '12px', color: alpha(theme.palette.text.primary, 0.72), lineHeight: 1.5 }}>
          {parts}
        </Typography>
      </Box>
    </Box>
  );
}
