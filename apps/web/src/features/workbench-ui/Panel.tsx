'use client';

import { Box, Paper, Stack, Typography } from '@mui/material';
import NextLink from 'next/link';
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
  href,
  severity,
}: {
  primary: ReactNode;
  secondary?: ReactNode;
  figure?: ReactNode;
  onClick?: () => void;
  href?: string;
  severity?: 'danger' | 'warning' | 'info' | 'neutral';
}) {
  const color =
    severity === 'danger' ? 'error.main' : severity === 'warning' ? 'warning.main' : severity === 'info' ? 'primary.main' : 'divider';
  const interactive = Boolean(href || onClick);
  const row = (
    <Box
      onClick={href ? undefined : onClick}
      role={href ? undefined : onClick ? 'button' : undefined}
      tabIndex={href ? undefined : onClick ? 0 : undefined}
      onKeyDown={href || !onClick ? undefined : (e) => (e.key === 'Enter' || e.key === ' ') && onClick()}
      sx={{
        display: 'flex',
        alignItems: 'center',
        gap: 1.5,
        py: 1,
        px: 1.5,
        borderLeft: '3px solid',
        borderColor: color,
        borderRadius: 1,
        cursor: interactive ? 'pointer' : 'default',
        '&:hover': interactive ? { bgcolor: 'action.hover' } : undefined,
        '&:focus-visible': { outline: '2px solid', outlineColor: 'primary.main', outlineOffset: 1 },
      }}
    >
      <Box sx={{ flex: 1, minWidth: 0 }}>
        <Typography variant="body2" component="div" sx={{ fontWeight: 500 }} noWrap>
          {primary}
        </Typography>
        {secondary ? (
          <Typography variant="caption" component="div" color="text.secondary" noWrap sx={{ display: 'block' }}>
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
  if (href) {
    return (
      <Box component={NextLink} href={href} sx={{ textDecoration: 'none', color: 'inherit', display: 'block' }}>
        {row}
      </Box>
    );
  }
  return row;
}
