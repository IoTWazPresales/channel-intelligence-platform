'use client';

import { Box } from '@mui/material';
import { alpha, useTheme } from '@mui/material/styles';
import type { ButtonHTMLAttributes, ReactNode } from 'react';

import { tokensFor } from '@/theme/cipTokens';

/** Fade any CSS colour, including a `color-mix()` ramp that MUI's alpha() cannot parse. */
export function markerAlpha(color: string, opacity: number): string {
  return color.startsWith('color-mix(')
    ? `color-mix(in srgb, ${color} ${Math.round(opacity * 100)}%, transparent)`
    : alpha(color, opacity);
}

type MarkerDotProps = {
  color: string;
  /** Diameter in px. The Shipments marker is 11, and 16 when selected. */
  size?: number;
  selected?: boolean;
  /** Dashed outline, no fill: a proposal that is not saved yet. */
  hollow?: boolean;
  /** The soft glow around a marker. Off for very dense maps. */
  glow?: boolean;
  children?: ReactNode;
  'data-testid'?: string;
};

/** The marker itself: Shipments' dot with its halo and glow, shared with Sell-through's pins. */
export function MarkerDot({
  color,
  size = 11,
  selected = false,
  hollow = false,
  glow = true,
  children,
  'data-testid': testId,
}: MarkerDotProps) {
  const t = tokensFor(useTheme().palette.mode);
  const box = hollow ? size + 3 : size;
  const halo = `0 0 0 ${selected ? 6 : 4}px ${markerAlpha(color, selected ? 0.28 : 0.18)}`;
  return (
    <Box
      component="span"
      data-marker-dot
      data-hollow={hollow}
      data-testid={testId}
      sx={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        flexShrink: 0,
        boxSizing: 'border-box',
        width: box,
        height: box,
        borderRadius: '50%',
        bgcolor: hollow ? 'transparent' : color,
        border: hollow ? `2px dashed ${color}` : undefined,
        fontSize: 10,
        fontWeight: 700,
        color: t.bg.default,
        boxShadow: glow ? `${halo}, 0 0 18px ${color}` : halo,
      }}
    >
      {children}
    </Box>
  );
}

type MapMarkerProps = Omit<ButtonHTMLAttributes<HTMLButtonElement>, 'color'> & {
  /** Position as a share of the map box, in percent. */
  x: number;
  y: number;
  /** On-screen nudge in px, for pins that would overlap. Never a coordinate change. */
  offset?: { dx: number; dy: number };
  /** Side of the square click target in px. */
  hit?: number;
  color: string;
  size?: number;
  selected?: boolean;
  hollow?: boolean;
  glow?: boolean;
  zIndex?: number;
  cursor?: string;
  touchAction?: string;
  children?: ReactNode;
};

/** One clickable marker on a shared map: Shipments' vessels and Sell-through's stores. */
export function MapMarker({
  x,
  y,
  offset,
  hit = 44,
  color,
  size,
  selected,
  hollow,
  glow,
  zIndex,
  cursor = 'pointer',
  touchAction,
  children,
  ...button
}: MapMarkerProps) {
  const t = tokensFor(useTheme().palette.mode);
  return (
    <Box
      component="button"
      type="button"
      {...button}
      sx={{
        position: 'absolute',
        left: `${x}%`,
        top: `${y}%`,
        transform: offset
          ? `translate(calc(-50% + ${offset.dx}px), calc(-50% + ${offset.dy}px))`
          : 'translate(-50%, -50%)',
        width: hit,
        height: hit,
        p: 0,
        border: 0,
        bgcolor: 'transparent',
        cursor,
        touchAction,
        zIndex,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        color: t.text.primary,
        '&:focus-visible': { outline: `2px solid ${t.accent.primary}`, outlineOffset: 2, borderRadius: '50%' },
      }}
    >
      <MarkerDot color={color} size={size} selected={selected} hollow={hollow} glow={glow}>
        {children}
      </MarkerDot>
    </Box>
  );
}
