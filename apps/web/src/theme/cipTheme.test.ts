import { describe, expect, it } from 'vitest';

import { createCipTheme } from '@/theme/cipTheme';
import { lightTokens, tokensFor } from '@/theme/cipTokens';

describe('createCipTheme color modes', () => {
  it('defaults to dark and keeps the existing cyan primary', () => {
    const theme = createCipTheme();
    expect(theme.palette.mode).toBe('dark');
    expect(theme.palette.primary.main).toBe('#3db8e8');
    expect(theme.palette.background.default).toBe('#14161a');
  });

  it('light mode uses the light token paper and a darker primary for text contrast', () => {
    const theme = createCipTheme('comfortable', 'light');
    expect(theme.palette.mode).toBe('light');
    expect(theme.palette.background.default).toBe(lightTokens.bg.default);
    expect(theme.palette.background.paper).toBe(lightTokens.bg.surface);
    expect(theme.palette.primary.main).toBe(lightTokens.accent.primary);
    expect(theme.palette.text.primary).toBe(lightTokens.text.primary);
    expect(theme.palette.error.main).toBe(lightTokens.semantic.danger);
  });

  it('tokensFor returns dark tokens unless light is asked', () => {
    expect(tokensFor('dark').bg.default).toBe('#14161a');
    expect(tokensFor('light').bg.default).toBe(lightTokens.bg.default);
  });

  it('matches the dashboard-v2 mockup tokens (docs/design/dashboard-v2) in both modes', () => {
    const dark = createCipTheme();
    expect(dark.palette.text.secondary).toBe('rgba(186, 198, 210, 0.82)');
    expect(dark.palette.divider).toBe('rgba(120, 160, 190, 0.22)');
    expect(dark.palette.background.elevated).toBe('#1a1d23');
    expect(dark.palette.background.paper).toBe('#22262e');
    expect(dark.typography.fontSize).toBe(13);
    expect(dark.typography.h1?.fontSize).toBe('1.6875rem');
    expect(dark.typography.h5?.fontSize).toBe('0.9375rem');
    expect(dark.palette.primary.contrastText).toBe('#14161a');
    const cssBody = dark.components?.MuiCssBaseline?.styleOverrides as { body?: { backgroundImage?: string } } | undefined;
    expect(cssBody?.body?.backgroundImage).toContain('radial-gradient(ellipse at 25% 0');
    expect(dark.shape.borderRadius).toBe(10);
    const light = createCipTheme('comfortable', 'light');
    expect(light.palette.text.secondary).toBe('rgba(40, 54, 68, 0.82)');
    expect(light.palette.divider).toBe('rgba(32, 52, 72, 0.14)');
    expect(light.palette.background.elevated).toBe('#ffffff');
    expect(light.palette.success.main).toBe('#1f7a4d');
    expect(light.palette.warning.main).toBe('#9a6418');
  });
});
