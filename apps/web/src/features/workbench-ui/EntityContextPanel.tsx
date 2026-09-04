'use client';

import CloseIcon from '@mui/icons-material/Close';
import OpenInNewIcon from '@mui/icons-material/OpenInNew';
import { Box, Button, Divider, Drawer, IconButton, Stack, Typography, useMediaQuery } from '@mui/material';
import { useTheme } from '@mui/material/styles';
import NextLink from 'next/link';
import type { ReactNode } from 'react';

/**
 * Universal drill-down surface: a right-hand context panel (full-screen sheet at 390px) that shows an
 * entity or record without leaving the grid, with related workflows across domains.
 */
export function EntityContextPanel({
  open,
  onClose,
  kicker,
  title,
  subtitle,
  figures,
  related,
  children,
  footer,
  width = 440,
}: {
  open: boolean;
  onClose: () => void;
  kicker?: string;
  title: string;
  subtitle?: string;
  figures?: ReactNode;
  related?: { label: string; href: string; hint?: string }[];
  children?: ReactNode;
  footer?: ReactNode;
  width?: number;
}) {
  const theme = useTheme();
  const isMobile = useMediaQuery(theme.breakpoints.down('md'));
  return (
    <Drawer
      anchor={isMobile ? 'bottom' : 'right'}
      open={open}
      onClose={onClose}
      PaperProps={{
        sx: {
          width: isMobile ? '100%' : width,
          height: isMobile ? '92vh' : '100%',
          borderRadius: isMobile ? '16px 16px 0 0' : 0,
          borderLeft: isMobile ? 'none' : '1px solid',
          borderColor: 'divider',
          display: 'flex',
          flexDirection: 'column',
        },
      }}
      data-testid="entity-context-panel"
    >
      <Box sx={{ px: 2.5, pt: 2, pb: 1.5, display: 'flex', alignItems: 'flex-start', gap: 1 }}>
        <Box sx={{ flex: 1, minWidth: 0 }}>
          {kicker ? (
            <Typography variant="caption" color="primary.main" sx={{ textTransform: 'uppercase', letterSpacing: '0.06em', fontWeight: 600 }}>
              {kicker}
            </Typography>
          ) : null}
          <Typography variant="h6" sx={{ fontWeight: 650, lineHeight: 1.2 }}>
            {title}
          </Typography>
          {subtitle ? (
            <Typography variant="body2" color="text.secondary">
              {subtitle}
            </Typography>
          ) : null}
        </Box>
        <IconButton aria-label="Close panel" onClick={onClose} size="small">
          <CloseIcon fontSize="small" />
        </IconButton>
      </Box>
      {figures ? <Box sx={{ px: 2.5, pb: 1.5 }}>{figures}</Box> : null}
      <Divider />
      <Box sx={{ flex: 1, overflowY: 'auto', px: 2.5, py: 2 }}>
        {children}
        {related?.length ? (
          <Box sx={{ mt: 3 }}>
            <Typography variant="caption" color="text.secondary" sx={{ textTransform: 'uppercase', letterSpacing: '0.06em' }}>
              Related workflows
            </Typography>
            <Stack spacing={0.5} sx={{ mt: 1 }}>
              {related.map((r) => (
                <Button
                  key={r.href}
                  component={NextLink}
                  href={r.href}
                  variant="text"
                  size="small"
                  endIcon={<OpenInNewIcon sx={{ fontSize: 14 }} />}
                  sx={{
                    justifyContent: 'space-between',
                    textAlign: 'left',
                    px: 1.25,
                    color: 'text.primary',
                    '& .MuiButton-endIcon': { color: 'text.disabled' },
                  }}
                >
                  <Box>
                    <Typography variant="body2" component="span" sx={{ fontWeight: 500 }}>
                      {r.label}
                    </Typography>
                    {r.hint ? (
                      <Typography variant="caption" color="text.secondary" sx={{ display: 'block' }}>
                        {r.hint}
                      </Typography>
                    ) : null}
                  </Box>
                </Button>
              ))}
            </Stack>
          </Box>
        ) : null}
      </Box>
      {footer ? (
        <>
          <Divider />
          <Box sx={{ px: 2.5, py: 1.5, display: 'flex', gap: 1, justifyContent: 'flex-end', flexWrap: 'wrap' }}>{footer}</Box>
        </>
      ) : null}
    </Drawer>
  );
}

export function KeyValueList({ items }: { items: { k: string; v: ReactNode }[] }) {
  return (
    <Box component="dl" sx={{ m: 0, display: 'grid', gridTemplateColumns: 'minmax(120px, 40%) 1fr', rowGap: 0.75, columnGap: 1.5 }}>
      {items.map((it) => (
        <Box key={it.k} sx={{ display: 'contents' }}>
          <Typography component="dt" variant="caption" color="text.secondary" sx={{ alignSelf: 'center' }}>
            {it.k}
          </Typography>
          <Typography component="dd" variant="body2" sx={{ m: 0, fontVariantNumeric: 'tabular-nums' }}>
            {it.v}
          </Typography>
        </Box>
      ))}
    </Box>
  );
}
