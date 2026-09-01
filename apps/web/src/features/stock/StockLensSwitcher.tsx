'use client';

import { Box, Link, Typography } from '@mui/material';
import { alpha, useTheme } from '@mui/material/styles';
import NextLink from 'next/link';
import { useRouter, useSearchParams } from 'next/navigation';
import { useCallback } from 'react';

import { STOCK_LENSES, type StockLensId } from '@/features/stock/stockLenses';

type StockLensSwitcherProps = {
  lens: StockLensId;
};

export function StockLensSwitcher({ lens }: StockLensSwitcherProps) {
  const theme = useTheme();
  const line = alpha(theme.palette.common.white, 0.12);
  const router = useRouter();
  const searchParams = useSearchParams();

  const setLens = useCallback(
    (next: StockLensId) => {
      const params = new URLSearchParams(searchParams?.toString() ?? '');
      params.set('lens', next);
      router.replace(`/stock?${params.toString()}`, { scroll: false });
    },
    [router, searchParams],
  );

  return (
    <Box
      role="tablist"
      aria-label="Stock lenses"
      data-testid="stock-lens-switcher"
      sx={{
        display: 'flex',
        gap: 0.25,
        borderBottom: `1px solid ${line}`,
        mb: 1.5,
      }}
    >
      {STOCK_LENSES.map((item) => {
        const active = item.id === lens;
        return (
          <Link
            key={item.id}
            component={NextLink}
            href={`/stock?lens=${item.id}`}
            role="tab"
            aria-selected={active}
            onClick={(e) => {
              e.preventDefault();
              setLens(item.id);
            }}
            sx={{
              fontSize: '12.5px',
              fontWeight: 500,
              color: active ? theme.palette.text.primary : alpha(theme.palette.text.primary, 0.45),
              px: 1.625,
              py: 1,
              pb: 1.125,
              borderBottom: '2px solid',
              borderColor: active ? '#3db8e8' : 'transparent',
              textDecoration: 'none',
              '&:hover': { color: theme.palette.text.primary },
            }}
          >
            {item.label}
          </Link>
        );
      })}
    </Box>
  );
}

export function StockTaskCrumb({ lens }: { lens: StockLensId }) {
  const theme = useTheme();
  const label = STOCK_LENSES.find((l) => l.id === lens)?.label ?? lens;
  return (
    <Typography sx={{ fontSize: '12px', color: alpha(theme.palette.text.primary, 0.45) }} data-testid="stock-task-crumb">
      Stock / <Box component="span" sx={{ color: alpha(theme.palette.text.primary, 0.72), fontWeight: 500 }}>{label}</Box>
    </Typography>
  );
}
