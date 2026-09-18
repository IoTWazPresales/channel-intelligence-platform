'use client';

import { Box, Typography } from '@mui/material';

import { formatDualMoneyLine, formatUsdMoney } from '@/features/cpor/fxDisplay';

/**
 * ZAR primary with booked USD alongside. Evaluated CporFxAnchorPanel (too large for
 * headline strips and grid cells) and HeadlineFigure caption (too secondary — neither
 * currency is "the" number).
 *
 * Pass usdAmount for a pre-summed booked USD (portfolio). Never pass a live quote.
 */
export function DualMoney({
  amount,
  currencyCode,
  roeSnapshot,
  missingRoe,
  usdAmount,
  usdNote,
  testId = 'dual-money',
}: {
  amount: number | null | undefined;
  currencyCode?: string | null;
  roeSnapshot?: number | null;
  missingRoe?: boolean;
  usdAmount?: number | null;
  usdNote?: string;
  testId?: string;
}) {
  const dual = formatDualMoneyLine(amount, { currencyCode, roeSnapshot, missingRoe });
  let usdLine = dual.usdLine;
  if (usdAmount != null) {
    usdLine = `${formatUsdMoney(usdAmount)}${usdNote ? ` · ${usdNote}` : ' · Σ booked cases'}`;
  } else if (usdNote && missingRoe) {
    usdLine = usdNote;
  }
  const booked = usdAmount != null || dual.booked;
  return (
    <Box component="span" data-testid={testId} sx={{ display: 'inline-block', lineHeight: 1.15 }}>
      <Typography
        component="span"
        sx={{ font: 'inherit', fontVariantNumeric: 'tabular-nums', display: 'block' }}
      >
        {dual.local}
      </Typography>
      <Typography
        component="span"
        data-testid={`${testId}-usd`}
        sx={{
          display: 'block',
          fontSize: '0.55em',
          fontWeight: 500,
          color: booked ? 'text.secondary' : 'warning.main',
          letterSpacing: 0,
          textTransform: 'none',
          mt: 0.25,
        }}
      >
        {usdLine}
      </Typography>
    </Box>
  );
}
