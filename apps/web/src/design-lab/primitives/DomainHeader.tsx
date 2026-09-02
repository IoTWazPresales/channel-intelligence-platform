'use client';

import { Box, Breadcrumbs, Link, Stack, Typography } from '@mui/material';
import NextLink from 'next/link';
import type { ReactNode } from 'react';

/**
 * Evolution of `components/PageHeader.tsx`: adds a one-line "what this area does" description,
 * a meta slot (scope stamp / last refresh) and keeps actions on the same row at desktop.
 */
export function DomainHeader({
  crumbs,
  title,
  description,
  meta,
  actions,
}: {
  crumbs?: { label: string; href?: string }[];
  title: string;
  description?: string;
  meta?: ReactNode;
  actions?: ReactNode;
}) {
  return (
    <Box sx={{ mb: 2 }}>
      {crumbs?.length ? (
        <Breadcrumbs sx={{ mb: 0.5, '& .MuiBreadcrumbs-li': { fontSize: 12 } }}>
          {crumbs.map((c) =>
            c.href ? (
              <Link key={c.label} component={NextLink} href={c.href} underline="hover" color="inherit" variant="caption">
                {c.label}
              </Link>
            ) : (
              <Typography key={c.label} color="text.secondary" variant="caption">
                {c.label}
              </Typography>
            )
          )}
        </Breadcrumbs>
      ) : null}
      <Stack direction={{ xs: 'column', md: 'row' }} alignItems={{ md: 'flex-end' }} justifyContent="space-between" spacing={1}>
        <Box sx={{ minWidth: 0 }}>
          <Typography variant="h5" component="h1" sx={{ fontWeight: 650, letterSpacing: '-0.01em', lineHeight: 1.2 }}>
            {title}
          </Typography>
          {description ? (
            <Typography variant="body2" color="text.secondary" sx={{ mt: 0.5, maxWidth: 820 }}>
              {description}
            </Typography>
          ) : null}
          {meta ? (
            <Typography variant="caption" color="text.disabled" sx={{ display: 'block', mt: 0.5 }}>
              {meta}
            </Typography>
          ) : null}
        </Box>
        {actions ? (
          <Stack direction="row" spacing={1} useFlexGap sx={{ flexShrink: 0, flexWrap: 'wrap', maxWidth: '100%' }}>
            {actions}
          </Stack>
        ) : null}
      </Stack>
    </Box>
  );
}
