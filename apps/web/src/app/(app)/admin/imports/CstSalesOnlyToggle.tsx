'use client';

import { Checkbox, FormControlLabel, FormHelperText, Stack } from '@mui/material';

type Props = {
  checked: boolean;
  onChange: (checked: boolean) => void;
  disabled?: boolean;
  testId?: string;
};

/**
 * N-0110: a customer sell-through file with units and no on-hand column is refused
 * unless the operator marks the upload as sales-only.
 */
export function CstSalesOnlyToggle({ checked, onChange, disabled, testId = 'cst-sales-only' }: Props) {
  const helpId = `${testId}-help`;
  return (
    <Stack spacing={0}>
      <FormControlLabel
        control={
          <Checkbox
            checked={checked}
            onChange={(e) => onChange(e.target.checked)}
            disabled={disabled}
            inputProps={{ 'aria-describedby': helpId, 'data-testid': testId } as Record<string, string>}
          />
        }
        label="Sales-only file (units, no on-hand)"
      />
      <FormHelperText id={helpId} sx={{ mt: -0.5, ml: 4 }}>
        A file without the customer&apos;s on-hand column is refused unless this is ticked. Sales-only
        units count toward the expected stock position, but the file is not a stock report.
      </FormHelperText>
    </Stack>
  );
}
