'use client';

import HistoryOutlinedIcon from '@mui/icons-material/HistoryOutlined';
import {
  Alert,
  Box,
  Button,
  Chip,
  Paper,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableRow,
  Typography,
} from '@mui/material';
import { useQuery } from '@tanstack/react-query';
import { useMemo } from 'react';

import { apiGet } from '@/lib/api';

export type DsiCoverageFlag = {
  distributor_id: number;
  distributor_name: string;
  signal: 'sellout' | 'soh';
  week_start: string;
  message: string;
};

export type DsiCoverageDistributor = {
  distributor_id: number;
  distributor_name: string;
  sellout: {
    weekly_active: boolean;
    covered_weeks: string[];
    missed_weeks: string[];
  };
  soh: {
    weekly_active: boolean;
    covered_weeks: string[];
    missed_weeks: string[];
  };
};

export type DsiCoverageResponse = {
  data_unavailable: boolean;
  source_id?: number | null;
  weeks: number;
  week_starts: string[];
  distributors: DsiCoverageDistributor[];
  flags: DsiCoverageFlag[];
};

function formatWeekLabel(iso: string): string {
  const d = new Date(`${iso}T12:00:00`);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleDateString(undefined, { day: 'numeric', month: 'short' });
}

function cellStatus(
  dist: DsiCoverageDistributor,
  week: string,
  signal: 'sellout' | 'soh'
): 'covered' | 'missed' | 'inactive' {
  const block = signal === 'sellout' ? dist.sellout : dist.soh;
  if (!block.weekly_active) return 'inactive';
  if (block.covered_weeks.includes(week)) return 'covered';
  if (block.missed_weeks.includes(week)) return 'missed';
  return 'inactive';
}

export type DsiCoveragePanelProps = {
  sourceId: number | null;
  weeks?: number;
  /** Show compact flag banner only (validate step). */
  flagsOnly?: boolean;
  onUploadHistorical?: () => void;
};

export function DsiCoveragePanel({
  sourceId,
  weeks = 12,
  flagsOnly = false,
  onUploadHistorical,
}: DsiCoveragePanelProps) {
  const { data, isLoading, isError } = useQuery({
    queryKey: ['dsi-coverage', sourceId, weeks],
    queryFn: ({ signal }) =>
      apiGet<DsiCoverageResponse>(
        `/api/v1/imports/dsi/coverage?weeks=${weeks}${sourceId != null ? `&source_id=${sourceId}` : ''}`,
        { signal }
      ),
    enabled: sourceId != null,
    staleTime: 60_000,
  });

  const flags = data?.flags ?? [];
  const recentFlags = useMemo(() => flags.slice(0, 8), [flags]);

  if (sourceId == null) return null;
  if (isLoading) {
    return (
      <Typography variant="body2" color="text.secondary" data-testid="dsi-coverage-loading">
        Loading weekly coverage…
      </Typography>
    );
  }
  if (isError || data?.data_unavailable) return null;

  if (flagsOnly) {
    if (!flags.length) return null;
    return (
      <Alert
        severity="warning"
        data-testid="dsi-missed-weeks-flag"
        action={
          onUploadHistorical ? (
            <Button
              color="inherit"
              size="small"
              startIcon={<HistoryOutlinedIcon />}
              onClick={onUploadHistorical}
              data-testid="dsi-upload-historical-backfill"
            >
              Historical upload
            </Button>
          ) : undefined
        }
      >
        <Typography variant="body2" fontWeight={600} gutterBottom>
          Missed weekly coverage detected (informational — does not block apply)
        </Typography>
        <Stack component="ul" sx={{ m: 0, pl: 2.5 }} spacing={0.25}>
          {recentFlags.map((f) => (
            <Typography component="li" variant="caption" key={`${f.distributor_id}-${f.signal}-${f.week_start}`}>
              {f.message}
            </Typography>
          ))}
        </Stack>
        {flags.length > recentFlags.length ? (
          <Typography variant="caption" color="text.secondary" display="block" sx={{ mt: 0.5 }}>
            +{flags.length - recentFlags.length} more — see coverage panel below
          </Typography>
        ) : null}
      </Alert>
    );
  }

  const distributors = (data?.distributors ?? []).filter(
    (d) => d.sellout.weekly_active || d.soh.weekly_active
  );
  const weekStarts = data?.week_starts ?? [];

  if (!distributors.length) {
    return (
      <Alert severity="info" data-testid="dsi-coverage-empty">
        No weekly-active distributors in the last {weeks} weeks for this source yet.
      </Alert>
    );
  }

  return (
    <Paper variant="outlined" sx={{ p: 2 }} data-testid="dsi-coverage-panel">
      <Stack spacing={1.5}>
        <Stack direction="row" alignItems="center" justifyContent="space-between" flexWrap="wrap" gap={1}>
          <Typography variant="subtitle2">Weekly DSI coverage (last {weeks} ISO weeks)</Typography>
          <Stack direction="row" gap={0.5}>
            <Chip size="small" label="Sell-out" variant="outlined" />
            <Chip size="small" label="SOH" variant="outlined" color="secondary" />
          </Stack>
        </Stack>
        <Typography variant="caption" color="text.secondary">
          Green = data present · Red = missed week for a weekly-active distributor · FLAG only — upload gaps do not
          block this week&apos;s apply.
        </Typography>
        <Box sx={{ overflowX: 'auto' }}>
          <Table size="small" data-testid="dsi-coverage-grid">
            <TableHead>
              <TableRow>
                <TableCell>Distributor</TableCell>
                <TableCell>Signal</TableCell>
                {weekStarts.map((w) => (
                  <TableCell key={w} align="center" sx={{ minWidth: 48, px: 0.5 }}>
                    <Typography variant="caption">{formatWeekLabel(w)}</Typography>
                  </TableCell>
                ))}
              </TableRow>
            </TableHead>
            <TableBody>
              {distributors.flatMap((dist) =>
                (['sellout', 'soh'] as const).map((signal) => {
                  const block = signal === 'sellout' ? dist.sellout : dist.soh;
                  if (!block.weekly_active) return null;
                  return (
                    <TableRow key={`${dist.distributor_id}-${signal}`}>
                      <TableCell>{dist.distributor_name}</TableCell>
                      <TableCell>{signal === 'sellout' ? 'Sell-out' : 'SOH'}</TableCell>
                      {weekStarts.map((w) => {
                        const status = cellStatus(dist, w, signal);
                        const bg =
                          status === 'covered'
                            ? 'success.light'
                            : status === 'missed'
                              ? 'error.light'
                              : 'action.hover';
                        return (
                          <TableCell
                            key={w}
                            align="center"
                            sx={{
                              px: 0.25,
                              bgcolor: bg,
                              opacity: status === 'inactive' ? 0.35 : 1,
                            }}
                            data-testid={`dsi-cov-${dist.distributor_id}-${signal}-${w}`}
                          >
                            {status === 'covered' ? '●' : status === 'missed' ? '○' : '·'}
                          </TableCell>
                        );
                      })}
                    </TableRow>
                  );
                })
              )}
            </TableBody>
          </Table>
        </Box>
        {flags.length ? (
          <Alert severity="warning" variant="outlined">
            {flags.length} missed week{flags.length === 1 ? '' : 's'} flagged across active distributors.
            {onUploadHistorical ? (
              <>
                {' '}
                <Button
                  size="small"
                  startIcon={<HistoryOutlinedIcon />}
                  onClick={onUploadHistorical}
                  data-testid="dsi-coverage-historical-cta"
                >
                  Upload historical backfill
                </Button>
              </>
            ) : null}
          </Alert>
        ) : null}
      </Stack>
    </Paper>
  );
}
