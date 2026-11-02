'use client';

import { FormControl, InputLabel, MenuItem, Select } from '@mui/material';

/**
 * How many categories a ranked-bar or column chart starts with when the widget saved no top N. The editor shows this number and
 * the renderer uses it, so what the editor says is what the chart does (GOV-008 minor: the editor said 15 and a column chart showed 10).
 */
export function defaultTopN(visual: string): number {
  return visual === 'hbar' ? 15 : 10;
}

export const EDITOR_TOP_N_CHOICES = [5, 10, 15, 25, 50] as const;

/** The editor's "Start with top" control. */
export function TopNSelect({ visual, value, onChange }: { visual: string; value: number | null | undefined; onChange: (n: number) => void }) {
  return (
    <FormControl size="small" fullWidth>
      <InputLabel id="builder-topn-label">Start with top</InputLabel>
      <Select labelId="builder-topn-label" label="Start with top" value={value ?? defaultTopN(visual)} onChange={(e) => onChange(Number(e.target.value))}>
        {EDITOR_TOP_N_CHOICES.map((n) => (
          <MenuItem key={n} value={n}>
            {n}
          </MenuItem>
        ))}
      </Select>
    </FormControl>
  );
}
