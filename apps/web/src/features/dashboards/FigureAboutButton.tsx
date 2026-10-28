'use client';

import InfoOutlinedIcon from '@mui/icons-material/InfoOutlined';
import { Box, IconButton, Tooltip } from '@mui/material';
import type { ReactNode } from 'react';

/** The figure's explanation, beside Edit, so the chart keeps the row. */
export function FigureAboutButton({ testId, children }: { testId: string; children: ReactNode }) {
  const formulaId = testId.replace('about', 'formula');
  return (
    <Tooltip
      title={
        <Box data-testid={formulaId} sx={{ maxWidth: 360 }}>
          {children}
        </Box>
      }
      describeChild
      enterDelay={200}
      slotProps={{ tooltip: { sx: { maxWidth: 380, p: 1 } } }}
    >
      <IconButton size="small" aria-label="About this figure" data-testid={testId}>
        <InfoOutlinedIcon fontSize="small" />
      </IconButton>
    </Tooltip>
  );
}
