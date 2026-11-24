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
  interface TypeBackground {
    elevated: string;
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
      fontSize: 13,
      h1: { fontSize: '1.6875rem', fontWeight: 650, lineHeight: 1.1, letterSpacing: '-0.04em' },
      h2: { fontWeight: 600, letterSpacing: '-0.02em', fontSize: '1.25rem', lineHeight: 1.15 },
      h3: { fontWeight: 600, fontSize: '1.0625rem', lineHeight: 1.2 },
      h4: { fontWeight: 600, fontSize: '1rem' },
      h5: { fontSize: '0.9375rem', fontWeight: 650, lineHeight: 1.2, letterSpacing: '-0.02em' },
      h6: { fontWeight: 600, fontSize: '0.875rem' },
      body1: { fontSize: 13, lineHeight: 1.45 },
      body2: { fontSize: 13, lineHeight: 1.45, color: t.text.secondary },
      caption: { fontSize: 11, lineHeight: 1.45, color: t.text.muted },
    },
    palette: {
      mode,
      primary: {
        main: t.accent.primary,
        contrastText: mode === 'dark' ? t.bg.default : '#ffffff',
      },
      secondary: {
        main: mode === 'dark' ? '#5fd4c8' : '#0f7a72',
        contrastText: mode === 'dark' ? t.bg.default : '#ffffff',
      },
      background: { default: t.bg.default, paper: t.bg.surface, elevated: t.bg.elevated },
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
            backgroundImage: `radial-gradient(ellipse at 25% 0, ${t.accent.primaryMuted}, transparent 52%), ${t.bg.default}`,
          },
        },
      },
      MuiPaper: {
        styleOverrides: {
          root: {
            position: 'relative',
            overflow: 'hidden',
            backgroundImage: 'none',
            backgroundColor: t.bg.surface,
            border: `1px solid ${t.border.subtle}`,
            boxShadow:
              mode === 'dark' ? '0 8px 28px rgba(0,0,0,0.25)' : '0 4px 20px rgba(20, 35, 50, 0.08)',
            borderRadius: t.radius.card,
            '&[data-cip-tone="danger"]::before, &[data-cip-tone="bad"]::before': {
              content: '""',
              position: 'absolute',
              top: 0,
              left: 0,
              right: 0,
              height: 3,
              backgroundColor: t.semantic.danger,
            },
            '&[data-cip-tone="warning"]::before, &[data-cip-tone="warn"]::before': {
              content: '""',
              position: 'absolute',
              top: 0,
              left: 0,
              right: 0,
              height: 3,
              backgroundColor: t.semantic.warning,
            },
            '&[data-cip-tone="success"]::before, &[data-cip-tone="good"]::before': {
              content: '""',
              position: 'absolute',
              top: 0,
              left: 0,
              right: 0,
              height: 3,
              backgroundColor: t.semantic.success,
            },
            '&[data-cip-tone="info"]::before, &[data-cip-tone="primary"]::before': {
              content: '""',
              position: 'absolute',
              top: 0,
              left: 0,
              right: 0,
              height: 3,
              backgroundColor: t.accent.primary,
            },
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
          root: {
            textTransform: 'none',
            fontWeight: 600,
            borderRadius: t.radius.control,
            minHeight: 34,
            padding: '6px 11px',
          },
          containedPrimary: {
            fontWeight: 700,
            boxShadow: 'none',
            '&:hover': { boxShadow: 'none' },
          },
          outlined: {
            borderColor: t.border.strong,
          },
        },
      },
      MuiOutlinedInput: {
        styleOverrides: {
          root: { minHeight: 34, borderRadius: t.radius.control },
        },
      },
      MuiChip: {
        styleOverrides: {
          root: {
            borderRadius: 7,
            height: 22,
            fontSize: 11,
            fontWeight: 500,
            '& .MuiChip-label': { paddingLeft: 9, paddingRight: 9 },
          },
          filled: {
            '&.MuiChip-colorPrimary, &.MuiChip-colorSuccess, &.MuiChip-colorWarning, &.MuiChip-colorError': {
              gap: 6,
              '&::before': {
                content: '""',
                width: 5,
                height: 5,
                borderRadius: '50%',
                backgroundColor: 'currentColor',
                opacity: 0.95,
                flexShrink: 0,
                marginLeft: 6,
              },
              '& .MuiChip-label': { paddingLeft: 0 },
            },
          },
        },
      },
      MuiAlert: {
        styleOverrides: {
          standard: ({ ownerState, theme }) => {
            const tone =
              ownerState.severity === 'error'
                ? theme.palette.error.main
                : ownerState.severity === 'warning'
                  ? theme.palette.warning.main
                  : ownerState.severity === 'success'
                    ? theme.palette.success.main
                    : theme.palette.info.main;
            return {
              borderTop: `3px solid ${tone}`,
              borderRadius: t.radius.card,
            };
          },
          outlined: ({ ownerState, theme }) => {
            const tone =
              ownerState.severity === 'error'
                ? theme.palette.error.main
                : ownerState.severity === 'warning'
                  ? theme.palette.warning.main
                  : ownerState.severity === 'success'
                    ? theme.palette.success.main
                    : theme.palette.info.main;
            return {
              borderTop: `3px solid ${tone}`,
              borderRadius: t.radius.card,
            };
          },
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