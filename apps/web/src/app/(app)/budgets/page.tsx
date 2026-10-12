'use client';

import type { ColDef } from 'ag-grid-community';
import {
  Button,
  Checkbox,
  FormControlLabel,
  Stack,
  TextField,
  ToggleButton,
  ToggleButtonGroup,
  Typography,
} from '@mui/material';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useEffect, useMemo, useState } from 'react';

import { EnterpriseDataGrid } from '@/components/EnterpriseDataGrid';
import { ModuleDataSection } from '@/components/ModuleDataSection';
import { FundingChrome } from '@/features/promotions-funding/FundingChrome';
import { apiGet, apiPost } from '@/lib/api';

type PositionRow = {
  product_line: string;
  landed_quarter: string;
  reserved: number;
  committed: number;
  consumed: number;
  released: number;
  paid: number;
  remaining: number;
  pending: number;
  cap: number | null;
  quarter_label: string;
  line_label: string;
  bucket: 'planned' | 'unplanned';
};

type EntryRow = {
  id: number;
  entry_type: string;
  product_line: string;
  landed_quarter: string;
  amount_usd: number | null;
  case_id: number | null;
  source_tag: string | null;
  created_at: string | null;
};

export default function BudgetsPage() {
  const queryClient = useQueryClient();
  const [picked, setPicked] = useState<PositionRow | null>(null);
  const [view, setView] = useState<'campaign' | 'non_campaign'>('campaign');
  const [bucket, setBucket] = useState<'all' | 'unplanned' | 'unknown'>('all');
  const [fromLine, setFromLine] = useState('');
  const [fromQuarter, setFromQuarter] = useState('');
  const [toLine, setToLine] = useState('');
  const [toQuarter, setToQuarter] = useState('');
  const [amount, setAmount] = useState('');
  const [confirmOver, setConfirmOver] = useState(false);
  const position = useQuery({
    queryKey: ['budgets', 'ledger', view],
    queryFn: ({ signal }) =>
      apiGet<{ data_unavailable: boolean; items: PositionRow[]; portfolio_cap_usd: number | null; view: string }>(
        `/api/v1/budgets/ledger?view=${view}`,
        { signal },
      ),
  });
  const entries = useQuery({
    queryKey: ['budgets', 'entries', view, picked?.product_line, picked?.landed_quarter],
    enabled: picked != null,
    queryFn: ({ signal }) =>
      apiGet<{ items: EntryRow[] }>(
        `/api/v1/budgets/ledger/entries?view=${view}&product_line=${encodeURIComponent(picked?.product_line ?? '')}&landed_quarter=${encodeURIComponent(picked?.landed_quarter ?? '')}`,
        { signal },
      ),
  });
  const positionCols = useMemo<ColDef<PositionRow>[]>(
    () => [
      { field: 'line_label', headerName: 'Product line', flex: 1 },
      { field: 'quarter_label', headerName: 'Quarter', width: 150 },
      { field: 'bucket', headerName: 'Bucket', width: 130, valueGetter: (params) => (params.data?.bucket === 'unplanned' ? 'Unplanned' : 'Planned') },
      { field: 'reserved', headerName: 'Reserved', width: 120 },
      { field: 'committed', headerName: 'Committed', width: 130 },
      { field: 'pending', headerName: 'Pending', width: 120 },
      { field: 'consumed', headerName: 'Consumed', width: 130 },
      { field: 'released', headerName: 'Released', width: 120 },
      { field: 'paid', headerName: 'Paid', width: 110 },
      { field: 'remaining', headerName: 'Remaining', width: 130 },
      {
        colId: 'cap',
        headerName: 'Cap',
        width: 110,
        valueGetter: (params) => (params.data?.cap == null ? 'No cap' : String(params.data.cap)),
      },
    ],
    [],
  );
  const entryCols = useMemo<ColDef<EntryRow>[]>(
    () => [
      { field: 'created_at', headerName: 'When', flex: 1 },
      { field: 'entry_type', headerName: 'Type', width: 140 },
      { field: 'amount_usd', headerName: 'USD', width: 120 },
      { field: 'case_id', headerName: 'Case', width: 100 },
      { field: 'source_tag', headerName: 'Source', width: 160 },
    ],
    [],
  );
  const rows = (position.data?.items ?? []).filter((row) => {
    if (bucket === 'unplanned') return row.bucket === 'unplanned';
    if (bucket === 'unknown') return !row.landed_quarter;
    return true;
  });
  const sourceRemaining = (position.data?.items ?? []).find(
    (row) => row.product_line === fromLine && row.landed_quarter === fromQuarter,
  )?.remaining;
  const amountNumber = Number(amount);
  const overRemaining =
    sourceRemaining != null && Number.isFinite(amountNumber) && amountNumber > sourceRemaining + 0.0001;
  useEffect(() => {
    if (!picked) return;
    setFromLine(picked.product_line);
    setFromQuarter(picked.landed_quarter);
  }, [picked]);
  const move = useMutation({
    mutationFn: () =>
      apiPost<{ written: number }>('/api/v1/budgets/ledger/transfer', {
        source_product_line: fromLine,
        source_landed_quarter: fromQuarter,
        dest_product_line: toLine,
        dest_landed_quarter: toQuarter,
        amount_usd: amountNumber,
        confirm_over: confirmOver,
      }),
    onSuccess: async () => {
      setAmount('');
      setConfirmOver(false);
      setPicked(null);
      await queryClient.invalidateQueries({ queryKey: ['budgets'] });
    },
  });

  return (
    <FundingChrome>
      <Stack spacing={2} sx={{ mt: 2 }}>
        <Typography variant="body2" color="text.secondary">
          Product line by quarter. The campaign view is the budget. Non-campaign is the other reserve and does not
          reduce remaining. Pending is proposed-case support. Unplanned means consumed with no reserve. A blank
          quarter is Unknown quarter. A move writes two transfer rows and does not delete anything.
          {position.data?.portfolio_cap_usd == null
            ? ' No portfolio cap is set.'
            : ` Portfolio cap is ${position.data.portfolio_cap_usd}.`}{' '}
          Caps flag and do not block.
        </Typography>
        <Stack direction="row" spacing={1}>
          <ToggleButtonGroup
            exclusive
            size="small"
            value={view}
            onChange={(_event, next: 'campaign' | 'non_campaign' | null) => {
              if (next) {
                setView(next);
                setPicked(null);
              }
            }}
            aria-label="Reserve view"
          >
            <ToggleButton value="campaign">Campaign</ToggleButton>
            <ToggleButton value="non_campaign">Non-campaign</ToggleButton>
          </ToggleButtonGroup>
          <ToggleButtonGroup
            exclusive
            size="small"
            value={bucket}
            onChange={(_event, next: 'all' | 'unplanned' | 'unknown' | null) => {
              if (next) setBucket(next);
            }}
            aria-label="Budget buckets"
          >
            <ToggleButton value="all">All</ToggleButton>
            <ToggleButton value="unplanned">Unplanned</ToggleButton>
            <ToggleButton value="unknown">Unknown quarter</ToggleButton>
          </ToggleButtonGroup>
        </Stack>
        {view === 'campaign' ? (
          <Stack spacing={1} component="form" aria-label="Move campaign reserve" onSubmit={(event) => {
            event.preventDefault();
            move.mutate();
          }}>
            <Typography variant="subtitle2">Move campaign reserve</Typography>
            <Stack direction="row" spacing={1} useFlexGap flexWrap="wrap">
              <TextField size="small" label="From product line" value={fromLine} onChange={(event) => setFromLine(event.target.value)} />
              <TextField size="small" label="From quarter" value={fromQuarter} onChange={(event) => setFromQuarter(event.target.value)} />
              <TextField size="small" label="To product line" value={toLine} onChange={(event) => setToLine(event.target.value)} />
              <TextField size="small" label="To quarter" value={toQuarter} onChange={(event) => setToQuarter(event.target.value)} />
              <TextField size="small" label="Amount USD" value={amount} onChange={(event) => setAmount(event.target.value)} inputProps={{ inputMode: 'decimal' }} />
              <Button type="submit" variant="outlined" disabled={move.isPending || !Number.isFinite(amountNumber) || amountNumber <= 0 || (overRemaining && !confirmOver)}>
                Move
              </Button>
            </Stack>
            {overRemaining ? (
              <FormControlLabel
                control={<Checkbox checked={confirmOver} onChange={(event) => setConfirmOver(event.target.checked)} />}
                label={`Remaining is ${sourceRemaining}. Move it anyway.`}
              />
            ) : null}
            {move.isError ? (
              <Typography variant="body2" color="error" role="alert">
                {move.error instanceof Error ? move.error.message : 'The move was not written.'}
              </Typography>
            ) : null}
          </Stack>
        ) : null}
        <ModuleDataSection
          isLoading={position.isLoading}
          isError={position.isError || position.data?.data_unavailable === true}
          error={position.isError || position.data?.data_unavailable ? new Error('Budget ledger is not available.') : null}
          isEmpty={!position.isLoading && rows.length === 0}
          empty={{
            title: view === 'non_campaign' ? 'No non-campaign reserve' : 'No budget entries',
            description:
              view === 'non_campaign'
                ? 'A lineup approval writes the non-campaign reserve. Nothing has been written yet.'
                : 'Approved lineup reserves and settled cases will appear here.',
          }}
        >
          <EnterpriseDataGrid<PositionRow>
            rowData={rows}
            columnDefs={positionCols}
            height={360}
            gridOptions={{ onRowClicked: (event) => setPicked(event.data ?? null) }}
          />
        </ModuleDataSection>
        {picked ? (
          <Stack spacing={1}>
            <Typography variant="subtitle2">
              {picked.line_label || 'No product line'} · {picked.quarter_label || 'Unknown quarter'}
            </Typography>
            <EnterpriseDataGrid<EntryRow>
              rowData={entries.data?.items ?? []}
              columnDefs={entryCols}
              height={280}
            />
          </Stack>
        ) : null}
      </Stack>
    </FundingChrome>
  );
}
