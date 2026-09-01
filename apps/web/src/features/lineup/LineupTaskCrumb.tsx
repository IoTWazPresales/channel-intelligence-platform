'use client';

import { Typography } from '@mui/material';
import { alpha, useTheme } from '@mui/material/styles';

import { lineupTaskSubtitle, type LineupScope } from '@/features/lineup/lineupViews';

export function LineupTaskCrumb({ scope }: { scope: LineupScope }) {
  const theme = useTheme();
  const subtitle = lineupTaskSubtitle(scope);
  return (
    <Typography
      component="div"
      data-testid="lineup-task-crumb"
      sx={{ fontSize: '12px', color: alpha(theme.palette.text.primary, 0.45) }}
    >
      Lineup /{' '}
      <Typography component="span" sx={{ color: alpha(theme.palette.text.primary, 0.72), fontWeight: 500 }}>
        {subtitle}
      </Typography>
    </Typography>
  );
}
