'use client';

import { Box } from '@mui/material';
import { alpha } from '@mui/material/styles';
import type { ReactNode } from 'react';

import type { tokensFor } from '@/theme/cipTokens';

type Tok = ReturnType<typeof tokensFor>;

/** Shipments places the hover card to the left or right of the marker past the map midpoint. */
export function mapHoverOpensRight(x: number): boolean {
  return x > 55;
}

type MapHoverCardProps = {
  x: number;
  y: number;
  t: Tok;
  testId: string;
  children: ReactNode;
  /** Border accent; defaults to theme primary (vessel selection uses warning for clusters). */
  borderColor?: string;
  width?: number;
};

/** Tooltip shell shared by On the water and Sell-through: position, blur panel, shadow. */
export function MapHoverCard({
  x, y, t, testId, children, borderColor, width = 300,
}: MapHoverCardProps) {
  const accent = borderColor ?? t.accent.primary;
  const right = mapHoverOpensRight(x);
  return (
    <Box
      role="tooltip"
      data-testid={testId}
      sx={{
        position: 'absolute',
        zIndex: 5,
        width,
        maxWidth: 'min(300px, 92%)',
        top: `calc(${y}% - 12px)`,
        ...(right ? { right: `calc(${100 - x}% + 26px)` } : { left: `calc(${x}% + 26px)` }),
        transform: 'translateY(-50%)',
        p: 1.5,
        borderRadius: 1.25,
        bgcolor: alpha(t.bg.default, 0.97),
        border: `1px solid ${alpha(accent, 0.6)}`,
        boxShadow: '0 12px 32px rgba(0,0,0,0.35)',
        pointerEvents: 'none',
      }}
    >
      {children}
    </Box>
  );
}

export function MapHoverSectionLabel({ t, children }: { t: Tok; children: ReactNode }) {
  return (
    <Box sx={{ fontSize: 11, letterSpacing: '.06em', textTransform: 'uppercase', color: t.text.muted, mt: 1 }}>
      {children}
    </Box>
  );
}

export function MapHoverTitleRow({ children }: { children: ReactNode }) {
  return (
    <Box sx={{ display: 'flex', justifyContent: 'space-between', gap: 1.5, alignItems: 'baseline' }}>
      {children}
    </Box>
  );
}