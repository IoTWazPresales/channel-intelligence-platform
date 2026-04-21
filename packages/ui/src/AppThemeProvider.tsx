'use client';

import { CssBaseline, GlobalStyles, ThemeProvider } from '@mui/material';
import type { Theme } from '@mui/material/styles';
import { ReactNode, useMemo } from 'react';

import { getDataDisplayGlobalStyles } from './agGridMuiTheme';
import { createEnterpriseTheme } from './theme';

export function AppThemeProvider({
  children,
  density = 'comfortable',
}: {
  children: ReactNode;
  density?: 'comfortable' | 'compact';
}) {
  const theme = useMemo(() => createEnterpriseTheme(density), [density]);
  return (
    <ThemeProvider theme={theme}>
      <CssBaseline />
      <GlobalStyles styles={(t) => getDataDisplayGlobalStyles(t as Theme)} />
      {children}
    </ThemeProvider>
  );
}
