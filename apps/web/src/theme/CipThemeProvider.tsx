'use client';

import { CssBaseline, GlobalStyles, ThemeProvider } from '@mui/material';
import type { Theme } from '@mui/material/styles';
import { getDataDisplayGlobalStyles } from '@cip/ui';
import { ReactNode, useMemo } from 'react';

import type { ColorMode } from '@/stores/uiStore';
import { createCipTheme } from '@/theme/cipTheme';

export function CipThemeProvider({
  children,
  density = 'comfortable',
  mode = 'dark',
}: {
  children: ReactNode;
  density?: 'comfortable' | 'compact';
  mode?: ColorMode;
}) {
  const theme = useMemo(() => createCipTheme(density, mode), [density, mode]);
  return (
    <ThemeProvider theme={theme}>
      <CssBaseline />
      <GlobalStyles styles={(t) => getDataDisplayGlobalStyles(t as Theme)} />
      {children}
    </ThemeProvider>
  );
}
