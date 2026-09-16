import { createTheme, type ThemeOptions } from '@mui/material/styles';

import type { ColorMode } from '@/stores/uiStore';
import { tokensFor } from '@/theme/cipTokens';

declare module '@mui/material/styles' {
  interface Theme {
    density: 'comfortable' | 'compact';
  }
  interface ThemeOptions {
    density?: 'comfortable' | 'compact';
  }
}

export function createCipTheme(
  density: 'comfortable' | 'compact' = 'comfortable',
  mode: ColorMode = 'dark',
) {
  const t = tokensFor(mode);
  const spacingFactor = density === 'compact' ? 0.85 : 1;
  const base: ThemeOptions = {
    density,
    shape: {
      borderRadius: t.radius.control,
    },
    typography: {
      fontFamily: 'var(--font-inter, "Inter", "Segoe UI", system-ui, sans-serif)',
      h1: { fontWeight: 600, letterSpacing: '-0.02em' },
      h2: { fontWeight: 600, letterSpacing: '-0.02em' },
      h3: { fontWeight: 600 },
      h4: { fontWeight: 600 },
      h5: { fontWeight: 600 },
      h6: { fontWeight: 600 },
      body2: { color: t.text.secondary },
      caption: { color: t.text.muted },
    },
    palette: {
      mode,
      primary: {
        main: t.accent.primary,
        contrastText: mode === 'dark' ? '#0b0c0f' : '#ffffff',
      },
      secondary: {
        main: mode === 'dark' ? '#5fd4c8' : '#0f7a72',
        contrastText: mode === 'dark' ? '#0b0c0f' : '#ffffff',
      },
      background: { default: t.bg.default, paper: t.bg.surface },
      divider: t.border.subtle,
      text: { primary: t.text.primary, secondary: t.text.secondary },
      success: { main: t.semantic.success },
      warning: { main: t.semantic.warning },
      error: { main: t.semantic.danger },
    },
    components: {
      MuiCssBaseline: {
        styleOverrides: {
          html: { colorScheme: mode },
          body: {
            backgroundColor: t.bg.default,
            backgroundImage:
              mode === 'dark'
                ? 'radial-gradient(ellipse 120% 80% at 20% -10%, rgba(61, 184, 232, 0.08), transparent 55%)'
                : 'radial-gradient(ellipse 120% 80% at 20% -10%, rgba(21, 111, 156, 0.06), transparent 55%)',
          },
        },
      },
      MuiPaper: {
        styleOverrides: {
          root: {
            backgroundImage: 'none',
            backgroundColor: t.bg.surface,
            border: `1px solid ${t.border.subtle}`,
            boxShadow:
              mode === 'dark' ? '0 8px 28px rgba(0,0,0,0.35)' : '0 4px 20px rgba(20, 35, 50, 0.08)',
            borderRadius: t.radius.card,
          },
        },
      },
      MuiDrawer: {
        styleOverrides: {
          paper: {
            borderRight: `1px solid ${t.border.subtle}`,
            backgroundColor: t.bg.elevated,
          },
        },
      },
      MuiAppBar: {
        styleOverrides: {
          root: {
            backgroundColor: t.bg.elevated,
            borderBottom: `1px solid ${t.border.subtle}`,
            boxShadow: 'none',
          },
        },
      },
      MuiButton: {
        styleOverrides: {
          root: { textTransform: 'none', fontWeight: 600, borderRadius: t.radius.control },
        },
      },
      MuiChip: {
        styleOverrides: {
          root: { borderRadius: 8 },
        },
      },
      MuiTableContainer: {
        styleOverrides: {
          root: {
            backgroundColor: t.bg.surface,
            border: 'none',
            borderRadius: t.radius.control,
            backgroundImage: 'none',
            boxShadow: 'none',
            overflow: 'hidden',
          },
        },
      },
      MuiTable: {
        styleOverrides: {
          root: {
            backgroundColor: t.bg.surface,
          },
        },
      },
      MuiTableHead: {
        styleOverrides: {
          root: {
            backgroundColor: t.bg.surfaceMuted,
          },
        },
      },
      MuiTableRow: {
        styleOverrides: {
          root: {
            '&:last-of-type td': { borderBottom: 'none' },
          },
        },
      },
      MuiTableCell: {
        styleOverrides: {
          root: {
            borderColor: t.border.subtle,
            padding: density === 'compact' ? '6px 10px' : undefined,
          },
        },
      },
    },
  };

  return createTheme({
    ...base,
    density,
    spacing: (factor: number) => `${8 * factor * spacingFactor}px`,
  });
}
