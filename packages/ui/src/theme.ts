import { createTheme, ThemeOptions } from '@mui/material/styles';

import { tokens } from './tokens';

declare module '@mui/material/styles' {
  interface Theme {
    density: 'comfortable' | 'compact';
  }
  interface ThemeOptions {
    density?: 'comfortable' | 'compact';
  }
}

const base: ThemeOptions = {
  density: 'comfortable',
  shape: {
    borderRadius: tokens.radius.control,
  },
  typography: {
    fontFamily: 'var(--font-inter, "Inter", "Segoe UI", system-ui, sans-serif)',
    fontSize: 13,
    h1: { fontSize: '1.6875rem', fontWeight: 650, lineHeight: 1.1, letterSpacing: '-0.04em' },
    h2: { fontWeight: 600, letterSpacing: '-0.02em' },
    h3: { fontWeight: 600 },
    h4: { fontWeight: 600 },
    h5: { fontWeight: 600 },
    h6: { fontWeight: 600 },
    body1: { fontSize: 13, lineHeight: 1.45 },
    body2: { color: tokens.text.secondary, fontSize: 13, lineHeight: 1.45 },
    caption: { color: tokens.text.muted, fontSize: 11, lineHeight: 1.45 },
  },
  palette: {
    mode: 'dark',
    primary: { main: tokens.accent.primary, contrastText: tokens.bg.default },
    secondary: { main: '#5fd4c8', contrastText: tokens.bg.default },
    background: { default: tokens.bg.default, paper: tokens.bg.surface },
    divider: tokens.border.subtle,
    text: { primary: tokens.text.primary, secondary: tokens.text.secondary },
    success: { main: tokens.semantic.success },
    warning: { main: tokens.semantic.warning },
    error: { main: tokens.semantic.danger },
  },
  components: {
    MuiCssBaseline: {
      styleOverrides: {
        body: {
          backgroundColor: tokens.bg.default,
          backgroundImage: `radial-gradient(ellipse at 25% 0, ${tokens.accent.primaryMuted}, transparent 52%), ${tokens.bg.default}`,
        },
      },
    },
    MuiPaper: {
      styleOverrides: {
        root: {
          backgroundImage: 'none',
          border: `1px solid ${tokens.border.subtle}`,
          boxShadow: '0 8px 28px rgba(0,0,0,0.25)',
          borderRadius: tokens.radius.card,
        },
      },
    },
    MuiDrawer: {
      styleOverrides: {
        paper: {
          borderRight: `1px solid ${tokens.border.subtle}`,
          backgroundColor: tokens.bg.elevated,
        },
      },
    },
    MuiAppBar: {
      styleOverrides: {
        root: {
          backgroundColor: tokens.bg.elevated,
          borderBottom: `1px solid ${tokens.border.subtle}`,
          boxShadow: 'none',
        },
      },
    },
    MuiButton: {
      styleOverrides: {
        root: {
          textTransform: 'none',
          fontWeight: 600,
          borderRadius: tokens.radius.control,
          minHeight: 34,
          padding: '6px 11px',
        },
        containedPrimary: {
          fontWeight: 700,
          boxShadow: 'none',
          '&:hover': { boxShadow: 'none' },
        },
        outlined: {
          borderColor: tokens.border.strong,
        },
      },
    },
    MuiChip: {
      styleOverrides: {
        root: {
          borderRadius: 7,
          height: 22,
          fontSize: 11,
          fontWeight: 500,
        },
      },
    },
  },
};

export function createEnterpriseTheme(density: 'comfortable' | 'compact' = 'comfortable') {
  const spacingFactor = density === 'compact' ? 0.85 : 1;
  return createTheme({
    ...base,
    density,
    spacing: (factor: number) => `${8 * factor * spacingFactor}px`,
    components: {
      ...base.components,
      MuiTableContainer: {
        styleOverrides: {
          root: {
            backgroundColor: tokens.bg.surface,
            border: 'none',
            borderRadius: tokens.radius.control,
            backgroundImage: 'none',
            boxShadow: 'none',
            overflow: 'hidden',
          },
        },
      },
      MuiTable: {
        styleOverrides: {
          root: {
            backgroundColor: tokens.bg.surface,
          },
        },
      },
      MuiTableHead: {
        styleOverrides: {
          root: {
            backgroundColor: tokens.bg.surfaceMuted,
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
            borderColor: tokens.border.subtle,
            padding: density === 'compact' ? '6px 10px' : undefined,
          },
        },
      },
    },
  });
}