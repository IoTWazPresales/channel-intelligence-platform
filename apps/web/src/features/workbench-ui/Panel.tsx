'use client';

import { Box, Paper, Stack, Typography } from '@mui/material';
import type { ReactNode } from 'react';

/**
 * Analytical panel: title row (title · subtitle · actions) + body. Replaces the ad-hoc Card/Box
 * wrappers used across features; keeps the body edge-to-edge so grids and charts sit flush.
 */
export function Panel({
  title,
  subtitle,
  actions,
  children,
  flush = false,
  minHeight,
  sx,
}: {
  title?: ReactNode;
  subtitle?: ReactNode;
  actions?: ReactNode;
  children: ReactNode;
  flush?: boolean;
  minHeight?: number | string;
  sx?: object;
}) {
  return (
    <Paper elevation={0} sx={{ boxShadow: 'none', display: 'flex', flexDirection: 'column', minHeight, height: '100%', ...sx }}>
      {title || actions ? (
        <Stack direction="row" alignItems="flex-start" justifyContent="space-between" sx={{ px: 2, pt: 1.5, pb: 1, gap: 1 }}>
          <Box sx={{ minWidth: 0 }}>
            {title ? (
              <Typography variant="subtitle2" sx={{ fontWeight: 600, lineHeight: 1.3 }}>
                {title}
              </Typography>
            ) : null}
            {subtitle ? (
              <Typography variant="caption" color="text.secondary" sx={{ display: 'block' }}>
                {subtitle}
              </Typography>
            ) : null}
          </Box>
          {actions ? <Box sx={{ flexShrink: 0 }}>{actions}</Box> : null}
        </Stack>
      ) : null}
      <Box sx={{ px: flush ? 0 : 2, pb: flush ? 0 : 2, flex: 1, minHeight: 0 }}>{children}</Box>
    </Paper>
  );
}

/** Two-line text row used inside panels for lists of items with a figure on the right. */
export function PanelRow({
  primary,
  secondary,
  figure,
  onClick,
  severity,
}: {
  primary: ReactNode;
  secondary?: ReactNode;
  figure?: ReactNode;
  onClick?: () => void;
  severity?: 'danger' | 'warning' | 'info' | 'neutral';
}) {
  const color =
    severity === 'danger' ? 'error.main' : severity === 'warning' ? 'warning.main' : severity === 'info' ? 'primary.main' : 'divider';
  return (
    <Box
      onClick={onClick}
      role={onClick ? 'button' : undefined}
      tabIndex={onClick ? 0 : undefined}
      onKeyDown={onClick ? (e) => (e.key === 'Enter' || e.key === ' ') && onClick() : undefined}
      sx={{
        display: 'flex',
        alignItems: 'center',
        gap: 1.5,
        py: 1,
        px: 1.5,
        borderLeft: '3px solid',
        borderColor: color,
        borderRadius: 1,
        cursor: onClick ? 'pointer' : 'default',
        '&:hover': onClick ? { bgcolor: 'action.hover' } : undefined,
        '&:focus-visible': { outline: '2px solid', outlineColor: 'primary.main', outlineOffset: 1 },
      }}
    >
      <Box sx={{ flex: 1, minWidth: 0 }}>
        <Typography variant="body2" sx={{ fontWeight: 500 }} noWrap>
          {primary}
        </Typography>
        {secondary ? (
          <Typography variant="caption" color="text.secondary" noWrap sx={{ display: 'block' }}>
            {secondary}
          </Typography>
        ) : null}
      </Box>
      {figure !== undefined ? (
        <Typography component="div" variant="body2" sx={{ fontWeight: 600, fontVariantNumeric: 'tabular-nums', flexShrink: 0 }}>
          {figure}
        </Typography>
      ) : null}
    </Box>
  );
}
