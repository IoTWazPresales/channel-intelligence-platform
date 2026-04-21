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
      <Typography variant="h5" sx={{ mb: 2, fontWeight: 600 }}>
        {title}
      </Typography>
      {actions}
    </>
  );
}
