'use client';

import { Alert, Box, Typography } from '@mui/material';

import { buildFxMoneyDisplay } from '@/features/cpor/fxDisplay';

export function CporFxAnchorPanel({
  currencyCode,
  roeSnapshot,
  missingRoe,
  localAmount,
  usdAmount,
  localLabel = 'Case support',
}: {
  currencyCode?: string | null;
  roeSnapshot?: number | null;
  missingRoe?: boolean;
  localAmount?: number | null;
  usdAmount?: number | null;
  localLabel?: string;
}) {
  const fx = buildFxMoneyDisplay({
    currencyCode,
    roeSnapshot,
    missingRoe,
    localAmount,
    usdAmount,
    localLabel,
  });

  return (
    <Box
      data-testid="cpor-fx-anchor"
      sx={{
        p: 2,
        mb: 1.5,
        borderRadius: '6px',
        bgcolor: 'background.paper',
        border: '1px solid',
        borderColor: 'divider',
      }}
    >
      <Typography
        sx={{
          fontSize: '9.5px',
          letterSpacing: '0.1em',
          textTransform: 'uppercase',
          color: 'text.disabled',
          fontWeight: 600,
        }}
      >
        {fx.localLabel}
      </Typography>
      <Typography
        component="div"
        data-testid="cpor-fx-anchor-local"
        sx={{
          fontFamily: 'var(--font-mono, "IBM Plex Mono", ui-monospace, monospace)',
          fontSize: '34px',
          fontWeight: 500,
          lineHeight: 1.05,
          mt: 0.5,
          fontVariantNumeric: 'tabular-nums lining-nums',
        }}
      >
        {fx.localAmount}
      </Typography>
      {fx.fxUndeclared ? (
        <Alert severity="warning" sx={{ mt: 1, py: 0 }} data-testid="cpor-fx-undeclared">
          FX undeclared — USD totals are not shown as case truth until a case rate of exchange is
          recorded.
        </Alert>
      ) : fx.usdBasisLine ? (
        <Typography
          data-testid="cpor-fx-anchor-usd-basis"
          sx={{
            mt: 0.75,
            fontFamily: 'var(--font-mono, "IBM Plex Mono", ui-monospace, monospace)',
            fontSize: '11.5px',
            color: 'text.secondary',
          }}
        >
          {fx.usdBasisLine}
          <Typography component="span" sx={{ color: 'text.disabled', ml: 0.5 }}>
            (declared case terms)
          </Typography>
        </Typography>
      ) : null}
    </Box>
  );
}
