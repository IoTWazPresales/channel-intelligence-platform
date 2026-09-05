'use client';

import { Box } from '@mui/material';
import type { ReactNode } from 'react';

/**
 * Desktop inset from design-lab `LabShell` main: px 20 / pt 16 / pb 24 (md: 2.5 / 2 / 3).
 * AppShell stays flush so Attention can go edge-to-edge; workbench domains opt in here.
 */
export function WorkbenchCanvas({ children }: { children: ReactNode }) {
  return (
    <Box
      data-testid="workbench-canvas"
      sx={{
        px: { xs: 1.5, md: 2.5 },
        pt: { xs: 1.5, md: 2 },
        pb: { xs: 10, md: 3 },
      }}
    >
      {children}
    </Box>
  );
}
