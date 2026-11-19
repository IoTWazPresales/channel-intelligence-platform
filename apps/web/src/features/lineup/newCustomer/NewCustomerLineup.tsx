'use client';

import {
  Alert,
  Box,
  Button,
  Checkbox,
  FormControl,
  FormControlLabel,
  Radio,
  RadioGroup,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableRow,
  TextField,
  Typography,
} from '@mui/material';
import { useMutation, useQuery } from '@tanstack/react-query';
import NextLink from 'next/link';
import { useEffect, useMemo, useState } from 'react';

import { Panel } from '@/features/workbench-ui/Panel';
import { apiGet, apiPost } from '@/lib/api';

import { nextLineupQuarter } from '../lineupQuarter';
import {
  REPORTING_CUSTOMERS_PATH,
  SOURCE_OPTIONS,
  allProductIds,
  approveBody,
  approvePath,
  basisHeadline,
  evidenceText,
  proposalPath,
  toggleProduct,
} from './proposalModel';
import type { ApproveResult, Proposal, ReportingCustomer, SeedSource } from './types';

type Request = { customerId: number; source: SeedSource; periodStart: string };

function errText(e: unknown): string {
  return e instanceof Error ? e.message : 'Something went wrong.';
}

function plural(n: number): string {
  return n === 1 ? 'line' : 'lines';
}

/**
 * New-customer line-up: pick a reporting customer, a period and a seed source, review the proposed
 * lines (untick any), then approve. Nothing is written until Approve is pressed.
 */
export function NewCustomerLineup() {
  const [customerId, setCustomerId] = useState<number | ''>('');
  const [periodStart, setPeriodStart] = useState(() => nextLineupQuarter().periodStart);
  const [source, setSource] = useState<SeedSource | ''>('');
  const [requested, setRequested] = useState<Request | null>(null);
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [approved, setApproved] = useState<{ result: ApproveResult; customer: string } | null>(null);

  const customers = useQuery({
    queryKey: ['lineup', 'new-customer', 'reporting-customers'],
    queryFn: ({ signal }) =>
      apiGet<{ customers: ReportingCustomer[] }>(REPORTING_CUSTOMERS_PATH, { signal }),
    staleTime: 60_000,
  });

  const proposal = useQuery({
    queryKey: ['lineup', 'new-customer', 'proposal', requested],
    queryFn: ({ signal }) =>
      apiGet<Proposal>(proposalPath(requested!.customerId, requested!.source, requested!.periodStart), {
        signal,
      }),
    enabled: requested !== null,
    retry: false,
    staleTime: 0,
    gcTime: 0,
  });

  const data = proposal.data;
  useEffect(() => {
    if (data) setSelected(allProductIds(data));
  }, [data]);

  const approve = useMutation({
    mutationFn: (req: Request) =>
      apiPost<ApproveResult>(approvePath(req.customerId), approveBody(req.source, req.periodStart, selected)),
    onSuccess: (result) => {
      const name = data?.customer.name ?? '';
      setApproved({ result, customer: name });
      setRequested(null);
    },
  });

  const customerList = customers.data?.customers ?? [];
  const noCustomers = customers.isSuccess && customerList.length === 0;
  const canShow = customerId !== '' && source !== '' && periodStart !== '';

  const resetResult = () => {
    setRequested(null);
    setApproved(null);
    approve.reset();
  };

  const rows = useMemo(() => data?.lines ?? [], [data]);

  return (
    <Stack spacing={2}>
      <Panel
        title="1. Customer, period and seed source"
        subtitle="Only reporting customers (reports expected) can be given a line-up here."
      >
        <Stack spacing={2} sx={{ p: 2 }}>
          {noCustomers ? (
            <Alert severity="info">
              No reporting customers found. Mark a customer as reporting (reports expected) first.
            </Alert>
          ) : null}
          {customers.isError ? <Alert severity="error">{errText(customers.error)}</Alert> : null}
          <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2}>
            <TextField
              select
              label="Customer"
              size="small"
              value={customerId}
              onChange={(e) => {
                setCustomerId(e.target.value === '' ? '' : Number(e.target.value));
                resetResult();
              }}
              SelectProps={{ native: true }}
              InputLabelProps={{ shrink: true }}
              sx={{ minWidth: 280 }}
            >
              <option value="">Choose a customer</option>
              {customerList.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.name}
                </option>
              ))}
            </TextField>
            <TextField
              label="Period start"
              type="date"
              size="small"
              value={periodStart}
              onChange={(e) => {
                setPeriodStart(e.target.value);
                resetResult();
              }}
              InputLabelProps={{ shrink: true }}
              helperText="First day of the quarter the line-up is for."
            />
          </Stack>
          <FormControl>
            <Typography variant="subtitle2" sx={{ mb: 0.5 }}>
              Where should the proposed SKUs come from?
            </Typography>
            <RadioGroup
              value={source}
              onChange={(e) => {
                setSource(e.target.value as SeedSource);
                resetResult();
              }}
            >
              {SOURCE_OPTIONS.map((o) => (
                <Box key={o.value} sx={{ mb: 1 }}>
                  <FormControlLabel value={o.value} control={<Radio size="small" />} label={o.label} />
                  <Typography variant="caption" color="text.secondary" sx={{ display: 'block', ml: 4 }}>
                    {o.explanation}
                  </Typography>
                </Box>
              ))}
            </RadioGroup>
          </FormControl>
          <Box>
            <Button
              variant="contained"
              disabled={!canShow}
              onClick={() => {
                setApproved(null);
                approve.reset();
                setRequested({
                  customerId: customerId as number,
                  source: source as SeedSource,
                  periodStart,
                });
              }}
            >
              Show proposal
            </Button>
          </Box>
        </Stack>
      </Panel>

      {proposal.isError ? <Alert severity="warning">{errText(proposal.error)}</Alert> : null}

      {approved ? (
        <Alert severity="success">
          Approved {approved.result.approved_count} {plural(approved.result.approved_count)}
          {approved.customer ? ` for ${approved.customer}` : ''}, {approved.result.period_label}. Quantities
          are empty: set them in the line-up.{' '}
          <NextLink href="/lineup/cases">Open the line-up cases</NextLink>
        </Alert>
      ) : null}

      {data ? (
        <Panel
          title={`2. Review the proposed lines for ${data.customer.name}`}
          subtitle={data.period_label}
          actions={
            <Typography variant="caption" color="text.secondary">
              {selected.size} of {data.line_count} {plural(data.line_count)} selected
            </Typography>
          }
        >
          <Stack spacing={2} sx={{ p: 2 }}>
            <Typography variant="subtitle2">{basisHeadline(data)}</Typography>
            <Alert severity="info">{data.basis}</Alert>
            <Typography variant="caption" color="text.secondary">
              Quantities and prices are not invented: lines start with empty quantities. Untick any line you do
              not want, then approve.
            </Typography>
            {data.lines.length === 0 ? (
              <Alert severity="warning">
                No SKUs were found for this source and period. Try the other source.
              </Alert>
            ) : (
              <Table size="small">
                <TableHead>
                  <TableRow>
                    <TableCell padding="checkbox" />
                    <TableCell>SKU</TableCell>
                    <TableCell>Product</TableCell>
                    <TableCell>Evidence</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {rows.map((line) => (
                    <TableRow key={line.product_id} hover>
                      <TableCell padding="checkbox">
                        <Checkbox
                          size="small"
                          checked={selected.has(line.product_id)}
                          onChange={() => setSelected((prev) => toggleProduct(prev, line.product_id))}
                          inputProps={{ 'aria-label': `Include ${line.sku}` }}
                        />
                      </TableCell>
                      <TableCell>{line.sku}</TableCell>
                      <TableCell>{line.label}</TableCell>
                      <TableCell>{evidenceText(line)}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            )}
            {approve.isError ? <Alert severity="error">{errText(approve.error)}</Alert> : null}
            <Stack direction="row" spacing={1}>
              <Button
                variant="contained"
                color="primary"
                disabled={selected.size === 0 || approve.isPending || requested === null}
                onClick={() => requested && approve.mutate(requested)}
              >
                {selected.size === 0 ? 'Approve' : `Approve ${selected.size} ${plural(selected.size)}`}
              </Button>
              <Button variant="text" onClick={resetResult} disabled={approve.isPending}>
                Cancel
              </Button>
            </Stack>
          </Stack>
        </Panel>
      ) : null}
    </Stack>
  );
}
