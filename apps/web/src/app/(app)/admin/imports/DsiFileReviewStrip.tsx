'use client';

import {
  Alert,
  Autocomplete,
  Button,
  Checkbox,
  FormControlLabel,
  Paper,
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
import { useEffect, useMemo, useState } from 'react';

import { apiGet, apiPost, safeDisplayError } from '@/lib/api';

export type DsiFileDistributorStamp = {
  token?: string | null;
  reason?: string | null;
  confirmed?: boolean;
  distributor_id?: number | null;
  distributor_name?: string | null;
};

export type DsiFileSnapshotPeriodStamp = {
  token?: string | null;
  resolved_date?: string | null;
  reason?: string | null;
  confirmed?: boolean;
  source?: string | null;
};

export type DsiFileReviewStripProps = {
  jobId: number;
  filenames: string[];
  rowSubtotals?: Record<string, number> | null;
  excludedFiles?: string[] | null;
  fileDistributors?: Record<string, DsiFileDistributorStamp> | null;
  fileSnapshotPeriods?: Record<string, DsiFileSnapshotPeriodStamp> | null;
  /** Filenames that map stock_on_hand without snapshot_date — period stamp is required. */
  filesNeedingInventoryPeriod?: string[] | null;
  jobLoaded?: boolean;
  onChanged?: () => void;
};

type DistributorOption = {
  id: number;
  distributor_name: string;
  name?: string;
  distributor_code?: string | null;
};

function stampLabel(st: DsiFileDistributorStamp | undefined): string {
  if (!st) return 'Not proposed';
  if (st.distributor_name) return st.distributor_name;
  if (st.token) return String(st.token);
  return 'Missing — assign a distributor';
}

function stampReason(st: DsiFileDistributorStamp | undefined): string {
  if (!st?.reason) return '—';
  if (st.reason === 'banner_company_name') return 'Banner Company Name';
  if (st.reason === 'banner_company_name_resolved') return 'Banner → dim match';
  if (st.reason === 'steward_assigned') return 'Steward assigned';
  if (st.reason === 'missing') return 'No banner found';
  if (st.reason === 'cleared') return 'Cleared';
  return String(st.reason);
}

function periodLabel(st: DsiFileSnapshotPeriodStamp | undefined): string {
  if (!st) return '—';
  if (st.resolved_date && st.token) return `${st.token} → ${st.resolved_date}`;
  if (st.resolved_date) return String(st.resolved_date);
  if (st.token) return `${st.token} (unparsed)`;
  return 'No Application Date banner';
}

function periodReason(st: DsiFileSnapshotPeriodStamp | undefined): string {
  if (!st?.reason) return '—';
  if (st.reason === 'banner_application_date') return 'Banner Application Date';
  if (st.reason === 'banner_unparsed') return 'Banner found, could not parse';
  if (st.reason === 'steward_override') return 'Steward date override';
  if (st.reason === 'missing') return 'No banner found';
  if (st.reason === 'cleared') return 'Cleared';
  return String(st.reason);
}

function distributorOptionLabel(o: DistributorOption): string {
  const label = o.distributor_name || o.name || `Distributor #${o.id}`;
  return o.distributor_code ? `${label} (${o.distributor_code})` : label;
}

export function DsiFileReviewStrip({
  jobId,
  filenames,
  rowSubtotals,
  excludedFiles,
  fileDistributors,
  fileSnapshotPeriods,
  filesNeedingInventoryPeriod,
  jobLoaded = false,
  onChanged,
}: DsiFileReviewStripProps) {
  const initial = useMemo(() => new Set(excludedFiles ?? []), [excludedFiles]);
  const periodFilterActive = filesNeedingInventoryPeriod != null;
  const needsPeriod = useMemo(
    () => new Set(filesNeedingInventoryPeriod ?? []),
    [filesNeedingInventoryPeriod]
  );
  const [excluded, setExcluded] = useState<Set<string>>(initial);
  const [changeFor, setChangeFor] = useState<string | null>(null);
  const [periodEditFor, setPeriodEditFor] = useState<string | null>(null);
  const [periodDate, setPeriodDate] = useState('');
  const [distQ, setDistQ] = useState('');

  useEffect(() => {
    setExcluded(new Set(excludedFiles ?? []));
  }, [excludedFiles]);

  const exclusionMutation = useMutation({
    mutationFn: async (next: string[]) => {
      await apiPost(`/api/v1/imports/jobs/${jobId}/dsi-file-exclusions`, {
        excluded_filenames: next,
      });
    },
    onSuccess: () => onChanged?.(),
  });

  const confirmMutation = useMutation({
    mutationFn: async (body: {
      filename: string;
      confirm?: boolean;
      distributor_id?: number;
      clear?: boolean;
    }) => {
      await apiPost(`/api/v1/imports/jobs/${jobId}/dsi-file-distributors`, body);
    },
    onSuccess: () => {
      setChangeFor(null);
      setDistQ('');
      onChanged?.();
    },
  });

  const periodMutation = useMutation({
    mutationFn: async (body: {
      filename?: string;
      confirm?: boolean;
      clear?: boolean;
      resolved_date?: string;
      confirm_all_sniffed?: boolean;
    }) => {
      await apiPost(`/api/v1/imports/jobs/${jobId}/dsi-file-snapshot-periods`, body);
    },
    onSuccess: () => {
      setPeriodEditFor(null);
      setPeriodDate('');
      onChanged?.();
    },
  });

  const { data: distSearch } = useQuery({
    queryKey: ['dsi-file-strip-distributors', distQ],
    queryFn: ({ signal }) =>
      apiGet<{ items: DistributorOption[] } | DistributorOption[]>(
        `/api/v1/distributors?q=${encodeURIComponent(distQ)}&page_size=20`,
        { signal }
      ),
    enabled: Boolean(changeFor) && distQ.trim().length >= 1,
  });

  const distOptions: DistributorOption[] = useMemo(() => {
    if (!distSearch) return [];
    if (Array.isArray(distSearch)) return distSearch;
    return distSearch.items ?? [];
  }, [distSearch]);

  if (!filenames.length) return null;

  const toggle = (name: string) => {
    if (jobLoaded) return;
    const next = new Set(excluded);
    if (next.has(name)) next.delete(name);
    else next.add(name);
    setExcluded(next);
    void exclusionMutation.mutateAsync([...next]);
  };

  const actionError = exclusionMutation.error ?? confirmMutation.error ?? periodMutation.error;
  const sniffPending = filenames.filter((n) => {
    if (excluded.has(n)) return false;
    if (periodFilterActive && !needsPeriod.has(n)) return false;
    const st = fileSnapshotPeriods?.[n];
    return Boolean(st?.resolved_date) && !st?.confirmed;
  });

  return (
    <Paper variant="outlined" sx={{ p: 2 }} data-testid="dsi-file-review-strip">
      <Stack spacing={1}>
        <Typography variant="subtitle2">Batch files in this job</Typography>
        <Typography variant="caption" color="text.secondary">
          Confirm distributor (Company Name banner) per file. <strong>Inventory period</strong> (Application Date →
          ISO week Monday) is the SOH as-of stamp only — it does not replace Transaction / invoice date on sell-out
          layouts. Map invoice dates on the column-mapping tabs. Exclude a file to drop it before re-validate.
        </Typography>
        {sniffPending.length > 0 && !jobLoaded ? (
          <Button
            size="small"
            variant="outlined"
            disabled={periodMutation.isPending}
            onClick={() => void periodMutation.mutateAsync({ confirm_all_sniffed: true })}
            data-testid="dsi-file-period-confirm-all"
            sx={{ alignSelf: 'flex-start' }}
          >
            Confirm all sniffed periods ({sniffPending.length})
          </Button>
        ) : null}
        {actionError ? <Alert severity="error">{safeDisplayError(actionError)}</Alert> : null}
        <Table size="small">
          <TableHead>
            <TableRow>
              <TableCell>Include</TableCell>
              <TableCell>File</TableCell>
              <TableCell align="right">Rows</TableCell>
              <TableCell>Distributor</TableCell>
              <TableCell>Inventory period</TableCell>
              <TableCell>Status</TableCell>
              <TableCell align="right">Actions</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {filenames.map((name) => {
              const st = fileDistributors?.[name];
              const period = fileSnapshotPeriods?.[name];
              const confirmed = Boolean(st?.confirmed);
              const periodConfirmed = Boolean(period?.confirmed);
              const canConfirm = Boolean(st?.token || st?.distributor_id);
              const canConfirmPeriod = Boolean(period?.resolved_date);
              const excludedRow = excluded.has(name);
              const periodRequired = !periodFilterActive || needsPeriod.has(name);
              return (
                <TableRow key={name}>
                  <TableCell padding="checkbox">
                    <FormControlLabel
                      control={
                        <Checkbox
                          size="small"
                          checked={!excludedRow}
                          disabled={jobLoaded || exclusionMutation.isPending}
                          onChange={() => toggle(name)}
                          inputProps={{ 'aria-label': `include ${name}` }}
                        />
                      }
                      label=""
                    />
                  </TableCell>
                  <TableCell>{name}</TableCell>
                  <TableCell align="right">{rowSubtotals?.[name] ?? '—'}</TableCell>
                  <TableCell>
                    {changeFor === name ? (
                      <Autocomplete
                        size="small"
                        sx={{ minWidth: 220 }}
                        options={distOptions}
                        getOptionLabel={distributorOptionLabel}
                        filterOptions={(x) => x}
                        onInputChange={(_, v) => setDistQ(v)}
                        onChange={(_, opt) => {
                          if (!opt) return;
                          void confirmMutation.mutateAsync({
                            filename: name,
                            distributor_id: opt.id,
                            confirm: true,
                          });
                        }}
                        renderInput={(params) => (
                          <TextField {...params} label="Search distributor" autoFocus />
                        )}
                      />
                    ) : (
                      <>
                        <Typography variant="body2">{stampLabel(st)}</Typography>
                        <Typography variant="caption" color="text.secondary" display="block">
                          {stampReason(st)}
                        </Typography>
                      </>
                    )}
                  </TableCell>
                  <TableCell>
                    {!periodRequired ? (
                      <>
                        <Typography variant="body2">N/A</Typography>
                        <Typography variant="caption" color="text.secondary" display="block">
                          Sell-out — map invoice date on layout tabs
                        </Typography>
                      </>
                    ) : periodEditFor === name ? (
                      <Stack direction="row" spacing={0.5} alignItems="center">
                        <TextField
                          size="small"
                          type="date"
                          label="As-of (Monday)"
                          value={periodDate}
                          onChange={(e) => setPeriodDate(e.target.value)}
                          InputLabelProps={{ shrink: true }}
                          sx={{ minWidth: 160 }}
                        />
                        <Button
                          size="small"
                          variant="contained"
                          disabled={!periodDate || periodMutation.isPending}
                          onClick={() =>
                            void periodMutation.mutateAsync({
                              filename: name,
                              resolved_date: periodDate,
                              confirm: true,
                            })
                          }
                        >
                          Save
                        </Button>
                      </Stack>
                    ) : (
                      <>
                        <Typography variant="body2">{periodLabel(period)}</Typography>
                        <Typography variant="caption" color="text.secondary" display="block">
                          {periodReason(period)}
                        </Typography>
                      </>
                    )}
                  </TableCell>
                  <TableCell>
                    {excludedRow
                      ? 'Excluded'
                      : periodRequired
                        ? `${confirmed ? 'Dist ✓' : 'Dist?'} · ${periodConfirmed ? 'Period ✓' : period?.resolved_date ? 'Period?' : 'Period —'}`
                        : `${confirmed ? 'Dist ✓' : 'Dist?'} · Period N/A`}
                  </TableCell>
                  <TableCell align="right">
                    <Stack direction="row" spacing={0.5} justifyContent="flex-end" flexWrap="wrap">
                      {!excludedRow && !confirmed && canConfirm ? (
                        <Button
                          size="small"
                          variant="contained"
                          disabled={jobLoaded || confirmMutation.isPending}
                          onClick={() =>
                            void confirmMutation.mutateAsync({ filename: name, confirm: true })
                          }
                          data-testid={`dsi-file-dist-confirm-${name}`}
                        >
                          Confirm dist
                        </Button>
                      ) : null}
                      {periodRequired && !excludedRow && !periodConfirmed && canConfirmPeriod ? (
                        <Button
                          size="small"
                          variant="contained"
                          color="secondary"
                          disabled={jobLoaded || periodMutation.isPending}
                          onClick={() =>
                            void periodMutation.mutateAsync({ filename: name, confirm: true })
                          }
                          data-testid={`dsi-file-period-confirm-${name}`}
                        >
                          Confirm period
                        </Button>
                      ) : null}
                      {!excludedRow ? (
                        <Button
                          size="small"
                          disabled={jobLoaded || confirmMutation.isPending}
                          onClick={() => setChangeFor(changeFor === name ? null : name)}
                          data-testid={`dsi-file-dist-change-${name}`}
                        >
                          {changeFor === name ? 'Cancel' : 'Change dist'}
                        </Button>
                      ) : null}
                      {periodRequired && !excludedRow ? (
                        <Button
                          size="small"
                          disabled={jobLoaded || periodMutation.isPending}
                          onClick={() => {
                            if (periodEditFor === name) {
                              setPeriodEditFor(null);
                              setPeriodDate('');
                            } else {
                              setPeriodEditFor(name);
                              setPeriodDate(period?.resolved_date ?? '');
                            }
                          }}
                          data-testid={`dsi-file-period-override-${name}`}
                        >
                          {periodEditFor === name ? 'Cancel' : 'Set period'}
                        </Button>
                      ) : null}
                    </Stack>
                  </TableCell>
                </TableRow>
              );
            })}
          </TableBody>
        </Table>
      </Stack>
    </Paper>
  );
}
