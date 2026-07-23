'use client';

import CloseIcon from '@mui/icons-material/Close';
import { Box, IconButton, Stack, Typography } from '@mui/material';
import type { ReactNode } from 'react';

export type StewardDrawerChromeProps = {
  title: ReactNode;
  onClose: () => void;
  children: ReactNode;
  rootTestId: string;
  closeTestId: string;
  ariaLabel?: string;
};

/**
 * Sticky steward drawer chrome (aside + header + scroll body).
 * Importer-specific mapping bodies slot as children.
 */
export function StewardDrawerChrome({
  title,
  onClose,
  children,
  rootTestId,
  closeTestId,
  ariaLabel = 'Candidate steward',
}: StewardDrawerChromeProps) {
  return (
    <Box
      component="aside"
      role="complementary"
      aria-label={ariaLabel}
      data-testid={rootTestId}
      sx={{
        width: { xs: '100%', md: '40%' },
        minWidth: { md: 320 },
        maxWidth: '100%',
        flexShrink: 0,
        borderLeft: { md: 1 },
        borderColor: 'divider',
        bgcolor: 'background.paper',
        display: 'flex',
        flexDirection: 'column',
        maxHeight: { xs: 'none', md: 'min(72vh, calc(100vh - 96px))' },
        overflow: 'hidden',
        position: { md: 'sticky' },
        top: { md: 80 },
        alignSelf: { md: 'flex-start' },
      }}
    >
      <Stack
        direction="row"
        alignItems="center"
        justifyContent="space-between"
        sx={{ px: 2, py: 1.25, borderBottom: 1, borderColor: 'divider', flexShrink: 0 }}
      >
        <Typography variant="subtitle1">{title}</Typography>
        <IconButton size="small" aria-label="Close steward drawer" onClick={onClose} data-testid={closeTestId}>
          <CloseIcon fontSize="small" />
        </IconButton>
      </Stack>
      <Box sx={{ flex: 1, overflow: 'auto', px: 2, py: 1.5 }}>{children}</Box>
    </Box>
  );
}
