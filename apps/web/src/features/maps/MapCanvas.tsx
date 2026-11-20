'use client';

import { Box } from '@mui/material';
import { useTheme } from '@mui/material/styles';
import { forwardRef, useEffect, useImperativeHandle, useRef, type ReactNode } from 'react';

import { tokensFor } from '@/theme/cipTokens';

import { BASEMAP_DOTS, BASEMAP_SIZE } from './basemapDots';
import { MAP_ASPECT_RATIO, mapViewBox, type MapBounds } from './mapGeometry';

export type MapSize = { w: number; h: number };
export const DEFAULT_MAP_SIZE: MapSize = { w: BASEMAP_SIZE.width, h: BASEMAP_SIZE.height };

/** The same wrapping map/side-panel columns on Shipments and Sell-through. */
export function MapLayout({ children }: { children: ReactNode }) {
  return (
    <Box data-map-layout sx={{ display: 'flex', flexWrap: 'wrap', gap: 2, alignItems: 'stretch' }}>
      {children}
    </Box>
  );
}

export function MapAside({ children }: { children: ReactNode }) {
  return (
    <Box sx={{ flex: '1 1 360px', minWidth: 'min(360px, 100%)', display: 'flex', flexDirection: 'column', gap: 1.5 }}>
      {children}
    </Box>
  );
}

/** Container extracted from On the water, including its padding, theme and column width. */
export function MapPanel({ children }: { children: ReactNode }) {
  const theme = useTheme();
  const t = tokensFor(theme.palette.mode);
  return (
    <Box
      data-map-panel
      sx={{
        flex: '999 1 600px', minWidth: 0, bgcolor: t.bg.surface,
        border: `1px solid ${t.border.subtle}`, borderRadius: 1.5, p: 1.75,
        display: 'flex', flexDirection: 'column', gap: 1.25,
        background: theme.palette.mode === 'dark'
          ? 'radial-gradient(ellipse at 60% 55%, #18222c 0%, #121519 70%)'
          : 'radial-gradient(ellipse at 60% 55%, #e6eef3 0%, #f6f9fb 70%)',
      }}
    >
      {children}
    </Box>
  );
}

type MapCanvasProps = {
  'data-testid': string;
  label: string;
  bounds?: MapBounds;
  svgChildren?: ReactNode;
  children?: ReactNode;
  onSizeChange?: (size: MapSize) => void;
};

/** One basemap and one box ratio; SVG and HTML overlays share the same projection. */
export const MapCanvas = forwardRef<HTMLDivElement, MapCanvasProps>(function MapCanvas(
  { label, bounds, svgChildren, children, onSizeChange, 'data-testid': testId }, ref,
) {
  const theme = useTheme();
  const canvasRef = useRef<HTMLDivElement>(null);
  useImperativeHandle(ref, () => canvasRef.current!);
  useEffect(() => {
    const el = canvasRef.current;
    if (!el || !onSizeChange) return;
    const measure = () => onSizeChange({
      w: el.clientWidth || DEFAULT_MAP_SIZE.w,
      h: el.clientHeight || DEFAULT_MAP_SIZE.h,
    });
    measure();
    if (typeof ResizeObserver === 'undefined') return;
    const observer = new ResizeObserver(measure);
    observer.observe(el);
    return () => observer.disconnect();
  }, [onSizeChange]);

  return (
    <Box
      ref={canvasRef}
      data-testid={testId}
      data-map-canvas
      sx={{ position: 'relative', width: '100%', aspectRatio: MAP_ASPECT_RATIO, borderRadius: 1, overflow: 'hidden' }}
    >
      <svg
        viewBox={mapViewBox(bounds)}
        role="img"
        aria-label={label}
        style={{ position: 'absolute', inset: 0, width: '100%', height: '100%', display: 'block', pointerEvents: 'none' }}
      >
        <path d={BASEMAP_DOTS} fill="none" stroke={theme.palette.mode === 'dark' ? 'rgba(160,185,205,0.28)' : 'rgba(40,70,95,0.30)'} strokeWidth="2.4" strokeLinecap="round" />
        {svgChildren}
      </svg>
      {children}
    </Box>
  );
});
