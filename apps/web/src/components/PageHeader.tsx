import { Breadcrumbs, Link, Typography } from '@mui/material';
import NextLink from 'next/link';
import { ReactNode } from 'react';

export function PageHeader({
  crumbs,
  title,
  actions,
}: {
  crumbs: { label: string; href?: string }[];
  title: string;
  actions?: ReactNode;
}) {
  return (
    <>
      {crumbs.length ? (
        <Breadcrumbs sx={{ mb: 1 }}>
          {crumbs.map((c) =>
            c.href ? (
              <Link key={c.label} component={NextLink} href={c.href} underline="hover" color="inherit" variant="body2">
                {c.label}
              </Link>
            ) : (
              <Typography key={c.label} color="text.secondary" variant="body2">
                {c.label}
              </Typography>
            )
          )}
        </Breadcrumbs>
      ) : null}
      {/* Theme h1 is the page title (dashboard-v2 mock-up). Warren 26 Nov: the element is an h1. */}
      <Typography variant="h1" component="h1" sx={{ mb: 2 }}>
        {title}
      </Typography>
      {actions}
    </>
  );
}
