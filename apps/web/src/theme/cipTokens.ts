import { tokens } from '@cip/ui';

import type { ColorMode } from '@/stores/uiStore';

/** Cool-grey light set in the same family as `@cip/ui` dark tokens; primary/semantics darkened for text-on-paper contrast. */
export const lightTokens = {
  bg: {
    default: '#f3f5f7',
    elevated: '#ffffff',
    surface: '#ffffff',
    surfaceMuted: '#e8edf1',
  },
  border: {
    subtle: 'rgba(32, 52, 72, 0.14)',
    strong: 'rgba(32, 52, 72, 0.28)',
  },
  text: {
    primary: 'rgba(16, 22, 30, 0.94)',
    secondary: 'rgba(40, 54, 68, 0.72)',
    muted: 'rgba(60, 76, 92, 0.58)',
  },
  accent: {
    primary: '#156f9c',
    primaryMuted: 'rgba(21, 111, 156, 0.12)',
  },
  semantic: {
    success: '#1f7a4d',
    warning: '#9a6418',
    danger: '#b13434',
  },
  radius: tokens.radius,
};

export function tokensFor(mode: ColorMode) {
  return mode === 'light' ? lightTokens : tokens;
}

