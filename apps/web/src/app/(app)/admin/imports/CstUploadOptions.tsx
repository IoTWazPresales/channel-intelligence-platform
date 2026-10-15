'use client';

import { Checkbox, FormControlLabel, FormHelperText, Stack, TextField } from '@mui/material';

import { CstSalesOnlyToggle } from './CstSalesOnlyToggle';

/** N-0111: what the uploader says about a customer sell-through file before it loads. */
export type CstUploadOptions = {
  salesOnly: boolean;
  stockOnly: boolean;
  /** Year of week (or month) numbers that carry none. Used only when `yearConfirmed`. */
  year: string;
  yearConfirmed: boolean;
};

export const EMPTY_CST_UPLOAD_OPTIONS: CstUploadOptions = {
  salesOnly: false,
  stockOnly: false,
  year: '',
  yearConfirmed: false,
};

const YEAR_IN_NAME = /(?<!\d)(20\d{2})(?!\d)/g;

/** The one year (2000-2099) the file names or their folders state; null when none or several. */
export function suggestYearFromNames(names: string[]): number | null {
  const years = new Set<number>();
  for (const name of names) {
    for (const m of name.matchAll(YEAR_IN_NAME)) years.add(Number(m[1]));
  }
  return years.size === 1 ? [...years][0] : null;
}

export function validYear(year: string): boolean {
  const n = Number(year);
  return /^\d{4}$/.test(year.trim()) && n >= 2000 && n <= 2099;
}

export function appendCstUploadOptions(fd: FormData, o: CstUploadOptions): void {
  if (o.salesOnly) fd.append('cst_sales_only', 'true');
  if (o.stockOnly) fd.append('cst_stock_only', 'true');
  if (o.yearConfirmed && validYear(o.year)) fd.append('cst_confirmed_year', o.year.trim());
}

type Props = {
  value: CstUploadOptions;
  onChange: (next: CstUploadOptions) => void;
  disabled?: boolean;
  testIdPrefix?: string;
};

/**
 * Sales only / Stock only / Year confirmed for a customer sell-through upload (N-0110, N-0111).
 * A newer file replaces only the figures it carries: sales-only never wipes stock and stock-only
 * never wipes sales. Week numbers without a year load only with a confirmed year.
 */
export function CstUploadOptionsFields({ value, onChange, disabled, testIdPrefix = 'cst' }: Props) {
  const stockHelpId = `${testIdPrefix}-stock-only-help`;
  const yearHelpId = `${testIdPrefix}-year-help`;
  const yearOk = validYear(value.year);
  return (
    <Stack spacing={1} data-testid={`${testIdPrefix}-upload-options`}>
      <CstSalesOnlyToggle
        checked={value.salesOnly}
        onChange={(checked) => onChange({ ...value, salesOnly: checked, stockOnly: checked ? false : value.stockOnly })}
        disabled={disabled}
        testId={`${testIdPrefix}-sales-only`}
      />
      <Stack spacing={0}>
        <FormControlLabel
          control={
            <Checkbox
              checked={value.stockOnly}
              onChange={(e) =>
                onChange({ ...value, stockOnly: e.target.checked, salesOnly: e.target.checked ? false : value.salesOnly })
              }
              disabled={disabled}
              inputProps={
                { 'aria-describedby': stockHelpId, 'data-testid': `${testIdPrefix}-stock-only` } as Record<string, string>
              }
            />
          }
          label="Stock-only file (on-hand, no units sold)"
        />
        <FormHelperText id={stockHelpId} sx={{ mt: -0.5, ml: 4 }}>
          A file without a units sold column is refused unless this is ticked. Its on-hand replaces only on-hand;
          units already loaded for those weeks stay.
        </FormHelperText>
      </Stack>
      <Stack direction="row" spacing={2} alignItems="flex-start">
        <TextField
          size="small"
          label="Year of the week numbers"
          value={value.year}
          onChange={(e) => onChange({ ...value, year: e.target.value.replace(/[^\d]/g, '').slice(0, 4), yearConfirmed: false })}
          disabled={disabled}
          inputProps={{ inputMode: 'numeric', 'aria-describedby': yearHelpId, 'data-testid': `${testIdPrefix}-year` }}
          error={value.year !== '' && !yearOk}
          sx={{ width: 200 }}
        />
        <FormControlLabel
          control={
            <Checkbox
              checked={value.yearConfirmed && yearOk}
              onChange={(e) => onChange({ ...value, yearConfirmed: e.target.checked })}
              disabled={disabled || !yearOk}
              inputProps={{ 'aria-describedby': yearHelpId, 'data-testid': `${testIdPrefix}-year-confirmed` } as Record<string, string>}
            />
          }
          label="Year confirmed"
        />
      </Stack>
      <FormHelperText id={yearHelpId} sx={{ mt: -0.5 }}>
        Only for files with week numbers and no dates. Pre-filled from the file name or folder when it names a year.
        Nothing from such a file loads until the year is confirmed. Files with a sale date per line need neither.
      </FormHelperText>
    </Stack>
  );
}
