export const tokens = {
  bg: {
    default: '#14161a',
    elevated: '#1a1d23',
    surface: '#22262e',
    surfaceMuted: '#2a2f38',
  },
  border: {
    subtle: 'rgba(120, 160, 190, 0.22)',
    strong: 'rgba(120, 160, 190, 0.35)',
  },
  text: {
    primary: 'rgba(245, 247, 250, 0.96)',
    secondary: 'rgba(186, 198, 210, 0.72)',
    muted: 'rgba(160, 176, 192, 0.55)',
  },
  accent: {
    primary: '#3db8e8',
    primaryMuted: 'rgba(61, 184, 232, 0.15)',
  },
  semantic: {
    success: '#3d9b6a',
    warning: '#d4a15a',
    danger: '#c45c5c',
  },
  radius: {
    card: 12,
    control: 10,
  },
} as const;
