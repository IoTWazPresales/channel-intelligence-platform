'use client';

/**
 * "View rows" (spec s.5, S11), honest version: v2 has no row-level endpoint, so this is the same
 * question at the finest breakdowns the model allows (up to 3), labelled as grouped rows, not single
 * transactions. Totals come from this grouped query; a finer grain can change non-additive measures.
 */

import CloseIcon from '@mui/icons-material/Close';
import { Alert, Box, Button, Drawer, IconButton, Stack, Typography, useMediaQuery } from '@mui/material';
import { useTheme } from '@mui/material/styles';
import { useMemo } from 'react';

import { EnterpriseDataGrid } from '@/components/EnterpriseDataGrid';
import { formatChartValue } from '@/features/workbench-ui/charts';

import { useV2Query } from './BuilderData';
import { breakdownLabel, definitionKind, measureOf, measureUnit, modelOf } from './catalog';
import { viewRowsBreakdowns, type RequestPlan } from './requestFor';
import { rowCount } from './shape';
import { downloadBlob, exportFileName, tableCols, toCsv } from './table';
import type { CatalogV2, DefinitionV2, V2Request, V2Row } from './types';
import { gridColumns } from './V2WidgetBody';

export function viewRowsRequest(def: DefinitionV2, plan: RequestPlan, catalog: CatalogV2 | null | undefined): { request: V2Request; breakdowns: string[] } | null {
  if (plan.status !== 'ready') return null;
  const kind = definitionKind(catalog, def);
  const own = def.query.breakdowns ?? [];
  if (kind === 'governed') return { request: { ...plan.request, limit: 5000 }, breakdowns: own };
  const first = measureOf(catalog, def.query.measures[0] ?? '');
  const model = modelOf(catalog, first?.model);
  // Only breakdowns every measure allows.
  const allowed = (model?.breakdowns ?? []).filter((b) => def.query.measures.every((m) => measureOf(catalog, m)?.breakdowns.includes(b) ?? true));
  const breakdowns = viewRowsBreakdowns(own, model?.id, allowed);
  const request: V2Request = { ...plan.request, breakdowns, limit: 5000 };
  delete request.sort;
  if (breakdowns.includes('period')) request.period = { ...(plan.request.period ?? {}), grain: plan.request.period?.grain ?? 'week' };
  return { request, breakdowns };
}

function grainWord(g: string | null | undefined) {
  return g ?? 'period';
}

export function ViewRowsDrawer({
  open,
  onClose,
  def,
  plan,
  catalog,
  title,
  dashboardName,
}: {
  open: boolean;
  onClose: () => void;
  def: DefinitionV2;
  plan: RequestPlan;
  catalog: CatalogV2 | null | undefined;
  title: string;
  dashboardName: string;
}) {
  const theme = useTheme();
  const phone = useMediaQuery(theme.breakpoints.down('sm'));
  const spec = useMemo(() => viewRowsRequest(def, plan, catalog), [def, plan, catalog]);
  const q = useV2Query(open && spec ? spec.request : null, { tag: 'view-rows' });
  const kind = definitionKind(catalog, def);
  const cols = useMemo(() => tableCols(q.data, (c) => measureUnit(measureOf(catalog, c.id))), [q.data, catalog]);
  const colDefs = useMemo(() => gridColumns(cols, undefined), [cols]);
  const grouped = (spec?.breakdowns ?? []).map((b) => (b === 'period' ? grainWord(spec?.request.period?.grain) : breakdownLabel(catalog, b).toLowerCase()));
  const heading =
    kind === 'governed'
      ? 'Rows behind this figure'
      : `Rows behind this figure — grouped by ${grouped.length ? grouped.join(', ').replace(/, ([^,]*)$/, ' and $1') : 'nothing (one total)'} (not single transactions)`;
  const firstMeasure = def.query.measures[0];
  const totalRaw = q.data?.totals?.[firstMeasure ?? ''];
  const total = typeof totalRaw === 'number' ? totalRaw : null;
  const unit = measureUnit(measureOf(catalog, firstMeasure ?? ''));
  const shown = q.data?.rows.length ?? 0;
  const count = rowCount(q.data);
  return (
    <Drawer
      anchor={phone ? 'bottom' : 'right'}
      open={open}
      onClose={onClose}
      slotProps={{ paper: { sx: { width: phone ? '100%' : 'min(920px, 92vw)', height: phone ? '100%' : undefined } } }}
      data-testid="view-rows-drawer"
    >
      <Stack sx={{ p: 2, height: '100%', minHeight: 0 }} spacing={1.5}>
        <Stack direction="row" alignItems="flex-start" spacing={1}>
          <Box sx={{ flex: 1, minWidth: 0 }}>
            <Typography variant="subtitle1" fontWeight={700} component="h2">
              {title}
            </Typography>
            <Typography variant="body2" color="text.secondary" data-testid="view-rows-heading">
              {def.display?.compare ? 'Current period only. ' : ''}
              {heading}
            </Typography>
            {kind === 'governed' ? (
              <Typography variant="caption" color="text.secondary" display="block">
                Channel Ops figures are worked out per their own grain; these are those rows.
              </Typography>
            ) : null}
          </Box>
          <IconButton aria-label="Close rows" onClick={onClose}>
            <CloseIcon />
          </IconButton>
        </Stack>
        {!spec ? <Alert severity="info">There is no query to show rows for.</Alert> : null}
        {q.isError ? <Alert severity="error">{String((q.error as Error)?.message ?? q.error)}</Alert> : null}
        {q.data && !q.data.ok ? (
          <Alert severity="warning" data-testid="view-rows-refused">
            {q.data.refusals.map((r) => r.reason).join(' ')}
          </Alert>
        ) : null}
        <Box sx={{ flex: 1, minHeight: 240 }}>
          {q.isLoading ? (
            <Typography variant="body2">Loading rows…</Typography>
          ) : q.data?.ok ? (
            <EnterpriseDataGrid<V2Row> rowData={q.data.rows} columnDefs={colDefs} height="100%" />
          ) : null}
        </Box>
        {q.data?.ok ? (
          <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1} alignItems={{ sm: 'center' }} data-testid="view-rows-footer">
            <Typography variant="body2" sx={{ flex: 1 }}>
              {total != null ? `Total at this grouping: ${formatChartValue(total, unit, 'full')}. ` : ''}
              {q.data.truncated
                ? `Showing ${shown.toLocaleString('en-US')} of ${count.toLocaleString('en-US')}; narrow the filters.`
                : `${count.toLocaleString('en-US')} rows.`}
            </Typography>
            <Button
              variant="outlined"
              size="small"
              onClick={() => downloadBlob(new Blob([toCsv(cols, q.data!.rows)], { type: 'text/csv;charset=utf-8' }), exportFileName(dashboardName, `${title} rows`, 'csv'))}
              data-testid="view-rows-export-csv"
            >
              Export CSV
            </Button>
          </Stack>
        ) : null}
      </Stack>
    </Drawer>
  );
}
