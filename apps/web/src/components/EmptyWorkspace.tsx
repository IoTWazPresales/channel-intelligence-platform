'use client';

import { Box, Button, Stack, Typography } from '@mui/material';
import NextLink from 'next/link';

export type EmptyWorkspaceAction = {
  label: string;
  href?: string;
  onClick?: () => void;
};

export function EmptyWorkspace({
  title,
  description,
  primary,
  secondary,
}: {
  title: string;
  description: string;
  primary?: EmptyWorkspaceAction;
  secondary?: EmptyWorkspaceAction;
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
        {primary ? <EmptyActionButton action={primary} variant="contained" /> : null}
        {secondary ? <EmptyActionButton action={secondary} variant="outlined" /> : null}
      </Stack>
    </Box>
  );
}

function EmptyActionButton({
  action,
  variant,
}: {
  action: EmptyWorkspaceAction;
  variant: 'contained' | 'outlined';
}) {
  if (action.onClick) {
    return (
      <Button variant={variant} onClick={action.onClick}>
        {action.label}
      </Button>
    );
  }
  if (action.href) {
    return (
      <Button variant={variant} component={NextLink} href={action.href}>
        {action.label}
      </Button>
    );
  }
  return null;
}
