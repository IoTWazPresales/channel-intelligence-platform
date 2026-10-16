'use client';

import { Alert, Button, Stack, TextField, Typography } from '@mui/material';
import { useMutation } from '@tanstack/react-query';
import { useEffect, useState } from 'react';

import { apiPost, safeDisplayError } from '@/lib/api';

export type DsiHeaderRowSheet = {
  sheet_name?: string | null;
  sheet_key?: string;
  source_file?: string;
  columns?: string[];
  /** 0-based row the headers were read from. */
  header_row?: number;
  header_row_user_set?: boolean;
  dsi_mappable?: boolean;
};

type Props = {
  jobId: number;
  sheets: DsiHeaderRowSheet[];
  /** Hide the control once the job is loaded: the header row can no longer change. */
  locked?: boolean;
  onChanged?: () => void;
};

function sheetLabel(s: DsiHeaderRowSheet, showName: boolean): string {
  const bits = [s.source_file, s.sheet_name].filter((x): x is string => Boolean(x));
  return showName && bits.length ? ` in ${bits.join(' / ')}` : '';
}

function HeaderRowLine({
  jobId,
  sheet,
  showName,
  locked,
  onChanged,
}: {
  jobId: number;
  sheet: DsiHeaderRowSheet;
  showName: boolean;
  locked: boolean;
  onChanged?: () => void;
}) {
  const shown = (sheet.header_row ?? 0) + 1;
  const [value, setValue] = useState(String(shown));
  useEffect(() => setValue(String(shown)), [shown]);

  const mutation = useMutation({
    mutationFn: async (row: number) => {
      await apiPost(`/api/v1/imports/jobs/${jobId}/dsi-header-row`, {
        header_row: row,
        filename: sheet.source_file ?? undefined,
        sheet_key: sheet.sheet_key ?? undefined,
      });
    },
    onSuccess: () => onChanged?.(),
  });

  const parsed = Number.parseInt(value, 10);
  const valid = Number.isInteger(parsed) && parsed >= 1 && parsed <= 200;
  const noHeaders = !(sheet.columns ?? []).some((c) => c && !/^unnamed:\s*\d+$/i.test(c));
  const key = sheet.sheet_key ?? 'sheet';

  return (
    <Stack spacing={0.5} data-testid={`dsi-header-row-${key}`}>
      <Stack direction="row" spacing={1.5} alignItems="center" flexWrap="wrap" useFlexGap>
        <Typography variant="body2" data-testid={`dsi-header-row-text-${key}`}>
          {noHeaders ? (
            <>
              <strong>No header row found</strong>
              {sheetLabel(sheet, showName)}
            </>
          ) : (
            <>
              Headers found on row <strong>{shown}</strong>
              {sheetLabel(sheet, showName)}
              {sheet.header_row_user_set ? ' (set by you)' : ''}
            </>
          )}
        </Typography>
        {locked ? null : (
          <>
            <TextField
              size="small"
              type="number"
              label="Headers on row"
              value={value}
              onChange={(e) => setValue(e.target.value)}
              error={!valid}
              slotProps={{ htmlInput: { min: 1, max: 200, 'aria-label': `Headers on row${sheetLabel(sheet, showName)}` } }}
              sx={{ width: 140 }}
            />
            <Button
              size="small"
              variant="outlined"
              disabled={!valid || parsed === shown || mutation.isPending}
              onClick={() => mutation.mutate(parsed)}
              data-testid={`dsi-header-row-apply-${key}`}
            >
              Re-read headers
            </Button>
          </>
        )}
      </Stack>
      {mutation.isError ? (
        <Alert severity="error" data-testid={`dsi-header-row-error-${key}`}>
          {safeDisplayError(mutation.error)}
        </Alert>
      ) : null}
      {!locked && !mutation.isError ? (
        <Typography variant="caption" color="text.secondary">
          Row numbers are as shown in the sheet. Changing this re-reads the columns and re-suggests this file&apos;s
          mapping.
        </Typography>
      ) : null}
    </Stack>
  );
}

/** The row the file's column names were read from, with a way to change it (DSI mapping step). */
export function DsiHeaderRowStrip({ jobId, sheets, locked = false, onChanged }: Props) {
  if (!sheets.length) return null;
  return (
    <Stack spacing={1} data-testid="dsi-header-row-strip">
      {sheets.map((s) => (
        <HeaderRowLine
          key={`${s.source_file ?? ''}::${s.sheet_key ?? ''}`}
          jobId={jobId}
          sheet={s}
          showName={sheets.length > 1}
          locked={locked}
          onChanged={onChanged}
        />
      ))}
    </Stack>
  );
}
