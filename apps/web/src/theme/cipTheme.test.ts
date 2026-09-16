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
});
