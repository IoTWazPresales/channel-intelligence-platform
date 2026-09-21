'use client';

import { Alert, Box, Stack, Table, TableBody, TableCell, TableHead, TableRow, Typography } from '@mui/material';
import { useQuery } from '@tanstack/react-query';
import { useMemo } from 'react';

import { ModuleDataSection } from '@/components/ModuleDataSection';
import { formatUsdMoney } from '@/features/cpor/fxDisplay';
import { apiGet } from '@/lib/api';

/** Shape of `GET /api/v1/cpor/cases/{id}/pivot`. Rows and columns are whatever grain the API pivots on. */
export type CporPivot = {
  cells: Record<string, Record<string, number>>;
  row_totals: Record<string, number>;
  col_totals: Record<string, number>;
  grand_total_usd: number;
  missing_roe: boolean;
};

/** Verbatim copy from the original workspace tab — the desk must not soften it. */
export const PIVOT_MISSING_ROE_COPY =
  'FX undeclared — USD pivot totals are withheld until a case rate of exchange is recorded.';

/**
 * USD pivot for one CPOR case, rendered as a table (the unmounted `CporCaseWorkspace` used a raw
 * `<pre>{JSON}</pre>`). Totals are withheld when the case has no declared rate of exchange, exactly
 * as before; the cells themselves are still shown so the operator can see the shape of the case.
 */
export function CporUsdPivotPanel({ caseId, roeSnapshot }: { caseId: number; roeSnapshot?: number | null }) {
  const q = useQuery({
    queryKey: ['cpor', 'pivot', caseId],
    queryFn: ({ signal }) => apiGet<CporPivot>(`/api/v1/cpor/cases/${caseId}/pivot`, { signal }),
    enabled: caseId > 0,
  });

  const rows = useMemo(() => Object.keys(q.data?.cells ?? {}).sort(), [q.data]);
  const cols = useMemo(() => {
    const seen = new Set<string>();
    for (const r of Object.values(q.data?.cells ?? {})) for (const c of Object.keys(r)) seen.add(c);
    return [...seen].sort();
  }, [q.data]);
  const withheld = q.data?.missing_roe === true;

  return (
    <ModuleDataSection
      isLoading={q.isLoading}
      isError={q.isError}
      error={q.isError ? new Error(String((q.error as Error)?.message ?? 'Failed to load USD pivot')) : null}
      onRetry={() => void q.refetch()}
      isEmpty={rows.length === 0}
      empty={{
        title: 'No USD pivot yet',
        description:
          'The pivot is built from approved case lines. Add lines and declare the case rate of exchange to see USD by product and period.',
      }}
      loadingLabel="Loading USD pivot…"
    >
      <Stack spacing={1} data-testid="cpor-usd-pivot">
        {withheld ? (
          <Alert severity="warning" data-testid="cpor-pivot-missing-roe">
            {PIVOT_MISSING_ROE_COPY}
          </Alert>
        ) : null}
        <Box sx={{ overflowX: 'auto' }}>
          <Table size="small" aria-label="USD pivot by row and column">
            <TableHead>
              <TableRow>
                <TableCell />
                {cols.map((c) => (
                  <TableCell key={c} align="right">
                    {c}
                  </TableCell>
                ))}
                {!withheld ? (
                  <TableCell align="right">
                    <strong>Total</strong>
                  </TableCell>
                ) : null}
              </TableRow>
            </TableHead>
            <TableBody>
              {rows.map((r) => (
                <TableRow key={r} data-testid={`cpor-pivot-row-${r}`}>
                  <TableCell component="th" scope="row">
                    {r}
                  </TableCell>
                  {cols.map((c) => (
                    <TableCell key={c} align="right">
                      {formatUsdMoney(q.data?.cells[r]?.[c])}
                    </TableCell>
                  ))}
                  {!withheld ? (
                    <TableCell align="right">
                      <strong>{formatUsdMoney(q.data?.row_totals[r])}</strong>
                    </TableCell>
                  ) : null}
                </TableRow>
              ))}
              {!withheld ? (
                <TableRow>
                  <TableCell component="th" scope="row">
                    <strong>Total</strong>
                  </TableCell>
                  {cols.map((c) => (
                    <TableCell key={c} align="right">
                      <strong>{formatUsdMoney(q.data?.col_totals[c])}</strong>
                    </TableCell>
                  ))}
                  <TableCell align="right" data-testid="cpor-pivot-grand-total">
                    <strong>{formatUsdMoney(q.data?.grand_total_usd)}</strong>
                  </TableCell>
                </TableRow>
              ) : null}
            </TableBody>
          </Table>
        </Box>
        {!withheld && roeSnapshot != null ? (
          <Typography variant="caption" color="text.secondary">
            Grand total USD {formatUsdMoney(q.data?.grand_total_usd)} at declared case rate ZAR {roeSnapshot.toFixed(2)}{' '}
            (declared case terms)
          </Typography>
        ) : null}
      </Stack>
    </ModuleDataSection>
  );
}
