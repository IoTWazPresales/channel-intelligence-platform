'use client';

import ArrowForwardIosIcon from '@mui/icons-material/ArrowForwardIos';
import { Box, Typography } from '@mui/material';
import { alpha, useTheme } from '@mui/material/styles';
import NextLink from 'next/link';
import type { ReactNode } from 'react';

/**
 * Start-a-job tile: title, short explanation, whole-card action.
 * Distinct from PanelRow (exception blotter) and from Import Center type-picker Cards.
 */
export function ActionCard({
  href,
  eyebrow,
  title,
  description,
  actionLabel = 'Open',
  testId,
}: {
  href: string;
  eyebrow?: ReactNode;
  title: ReactNode;
  description?: ReactNode;
  actionLabel?: string;
  testId?: string;
}) {
  const theme = useTheme();
  return (
    <Box
      component={NextLink}
      href={href}
      data-testid={testId}
      sx={{
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'stretch',
        minHeight: 92,
        height: '100%',
        px: 1.5,
        py: 1.25,
        textDecoration: 'none',
        color: 'inherit',
        border: '1px solid',
        borderColor: 'divider',
        borderRadius: 1.5,
        bgcolor: 'transparent',
        transition: 'border-color 120ms, background-color 120ms',
        '&:hover': {
          borderColor: 'primary.main',
          bgcolor: alpha(theme.palette.primary.main, 0.06),
        },
        '&:hover .action-card-go': {
          color: 'primary.main',
        },
        '&:focus-visible': {
          outline: '2px solid',
          outlineColor: 'primary.main',
          outlineOffset: 2,
        },
      }}
    >
      {eyebrow ? (
        <Typography
          variant="caption"
          color="text.secondary"
          sx={{
            display: 'block',
            textTransform: 'uppercase',
            letterSpacing: '0.08em',
            fontSize: 10,
            lineHeight: 1.2,
            mb: 0.5,
          }}
        >
          {eyebrow}
        </Typography>
      ) : null}
      <Typography component="div" sx={{ fontSize: 13, fontWeight: 600, lineHeight: 1.3 }}>
        {title}
      </Typography>
      {description ? (
        <Typography
          variant="caption"
          color="text.secondary"
          component="div"
          sx={{
            display: '-webkit-box',
            WebkitLineClamp: 2,
            WebkitBoxOrient: 'vertical',
            overflow: 'hidden',
            mt: 0.5,
            lineHeight: 1.35,
            flex: 1,
          }}
        >
          {description}
        </Typography>
      ) : null}
      <Box
        className="action-card-go"
        sx={{
          display: 'flex',
          alignItems: 'center',
          gap: 0.5,
          mt: 1,
          color: 'text.secondary',
          transition: 'color 120ms',
        }}
      >
        <Typography
          component="span"
          sx={{
            fontSize: 11,
            fontWeight: 600,
            letterSpacing: '0.06em',
            textTransform: 'uppercase',
          }}
        >
          {actionLabel}
        </Typography>
        <ArrowForwardIosIcon sx={{ fontSize: 10 }} />
      </Box>
    </Box>
  );
}
