'use client';

import { Box, Button, Stack, Typography } from '@mui/material';
import NextLink from 'next/link';

export function EmptyWorkspace({
  title,
  description,
  primary,
  secondary,
}: {
  title: string;
  description: string;
  primary?: { label: string; href: string };
  secondary?: { label: string; href: string };
}) {
  return (
    <Box
      role="region"
      aria-label={title}
      sx={{
        py: 6,
        px: 3,
        textAlign: 'center',
        border: '1px dashed',
        borderColor: 'divider',
        borderRadius: 2,
        bgcolor: 'action.hover',
      }}
    >
      <Typography variant="h6" fontWeight={600} gutterBottom>
        {title}
      </Typography>
      <Typography variant="body2" color="text.secondary" sx={{ maxWidth: 520, mx: 'auto', mb: 3 }}>
        {description}
      </Typography>
      <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2} justifyContent="center" alignItems="center">
        {primary ? (
          <Button variant="contained" component={NextLink} href={primary.href}>
            {primary.label}
          </Button>
        ) : null}
        {secondary ? (
          <Button variant="outlined" component={NextLink} href={secondary.href}>
            {secondary.label}
          </Button>
        ) : null}
      </Stack>
    </Box>
  );
}
