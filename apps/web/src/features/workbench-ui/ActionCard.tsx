'use client';

import ArrowForwardIosIcon from '@mui/icons-material/ArrowForwardIos';
import { Box, Card, Typography } from '@mui/material';
import { alpha, useTheme } from '@mui/material/styles';
import NextLink from 'next/link';
import type { ReactNode } from 'react';

/**
 * Start-a-job tile: title, short explanation, whole-card action.
 * Surface matches Import Center type-picker Cards (outlined, paper, no shadow).
 * Do not wrap a set of these in Panel or Card — N-0028 forbids a chrome wrapper around the strip.
 */
export function ActionCard({
  href,
  eyebrow,
  title,
  description,
  actionLabel = 'Open',
  testId,
  icon,
}: {
  href: string;
  eyebrow?: ReactNode;
  title: ReactNode;
  description?: ReactNode;
  actionLabel?: string;
  testId?: string;
  icon?: ReactNode;
}) {
  const theme = useTheme();
  return (
    <Card
      component={NextLink}
      href={href}
      variant="outlined"
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
        boxShadow: 'none',
        bgcolor: 'background.paper',
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
      <Box sx={{ display: 'flex', alignItems: 'flex-start', gap: 1 }}>
        {icon ? (
          <Box
            aria-hidden
            sx={{
              color: 'primary.main',
              display: 'flex',
              mt: 0.15,
              flexShrink: 0,
            }}
          >
            {icon}
          </Box>
        ) : null}
        <Box sx={{ minWidth: 0, flex: 1 }}>
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
          <Typography
            component="div"
            sx={{ fontSize: 16, fontWeight: 700, lineHeight: 1.3, letterSpacing: '-0.01em' }}
          >
            {title}
          </Typography>
        </Box>
      </Box>
      {description ? (
        <Typography
          variant="caption"
          color="text.secondary"
          component="div"
          sx={{
            display: '-webkit-box',
            WebkitLineClamp: 3,
            WebkitBoxOrient: 'vertical',
            overflow: 'hidden',
            mt: 0.75,
            lineHeight: 1.4,
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
    </Card>
  );
}
