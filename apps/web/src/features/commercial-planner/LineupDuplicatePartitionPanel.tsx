'use client';

import {
  Alert,
  Box,
  Button,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  Stack,
  Typography,
} from '@mui/material';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';

import { apiGet, apiPost } from '@/lib/api';

type Cluster = {
  file_name: string;
  inferred_period_start: string | null;
  line_count: number;
  case_ids: number[];
  business_units: string[];
};

type PreviewCase = {
  case_id: number;
  business_unit: string | null;
  target_product_line: string;
  lines_keep: number;
  lines_supersede: number;
  units_keep: number;
  units_supersede: number;
};

export function LineupDuplicatePartitionPanel() {
  const qc = useQueryClient();
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [selectedCluster, setSelectedCluster] = useState<Cluster | null>(null);

  const clustersQ = useQuery({
    queryKey: ['lineup-duplicate-clusters'],
    queryFn: () =>
      apiGet<{ cluster_count: number; clusters: Cluster[] }>(
        '/api/v1/commercial-planner/lineup/duplicate-ingestion/clusters',
      ),
  });

  const previewQ = useQuery({
    queryKey: ['lineup-duplicate-preview', selectedCluster?.case_ids],
    enabled: Boolean(selectedCluster?.case_ids?.length),
    queryFn: () =>
      apiPost<{ cases: PreviewCase[]; total_lines_to_supersede: number }>(
        '/api/v1/commercial-planner/lineup/duplicate-ingestion/partition/preview',
        { case_ids: selectedCluster!.case_ids, confirm: false },
      ),
  });

  const applyM = useMutation({
    mutationFn: () =>
      apiPost(
        '/api/v1/commercial-planner/lineup/duplicate-ingestion/partition/apply',
        { case_ids: selectedCluster!.case_ids, confirm: true },
      ),
    onSuccess: async () => {
      setConfirmOpen(false);
      setSelectedCluster(null);
      await qc.invalidateQueries({ queryKey: ['lineup-duplicate-clusters'] });
      await qc.invalidateQueries({ queryKey: ['po-management'] });
      await qc.invalidateQueries({ queryKey: ['plan-vs-executed'] });
    },
  });

  const count = clustersQ.data?.cluster_count ?? 0;
  if (!clustersQ.isLoading && count === 0) return null;

  return (
    <Alert severity="warning" data-testid="duplicate-ingestion-repair-panel">
      <Typography variant="subtitle2" sx={{ fontWeight: 600 }}>
        Duplicate lineup ingestion (BACKLOG-066)
      </Typography>
      <Typography variant="body2" sx={{ mt: 0.5 }}>
        {count} active cluster{count === 1 ? '' : 's'} — identical workbook fingerprints in multiple cases
        double-count planned units per BU. Partition keeps each case&apos;s own product_line lines only.
      </Typography>
      <Stack spacing={1} sx={{ mt: 1 }}>
        {(clustersQ.data?.clusters ?? []).map((c) => (
          <Box key={c.case_ids.join('-')}>
            <Typography variant="body2">
              Cases {c.case_ids.join(', ')} · {c.line_count} lines · BUs {c.business_units.join('/')} ·{' '}
              {c.file_name?.slice(-60)}
            </Typography>
            <Button
              size="small"
              variant="outlined"
              sx={{ mt: 0.5 }}
              onClick={() => {
                setSelectedCluster(c);
                setConfirmOpen(true);
              }}
            >
              Preview partition repair
            </Button>
          </Box>
        ))}
      </Stack>

      <Dialog open={confirmOpen} onClose={() => setConfirmOpen(false)} maxWidth="sm" fullWidth>
        <DialogTitle>Partition duplicate-ingestion lines</DialogTitle>
        <DialogContent>
          {previewQ.isLoading ? <Typography variant="body2">Loading preview…</Typography> : null}
          {previewQ.data ? (
            <Stack spacing={1}>
              {previewQ.data.cases.map((c) => (
                <Typography key={c.case_id} variant="body2">
                  Case #{c.case_id} ({c.business_unit}) → keep {c.lines_keep} lines / {c.units_keep} units;
                  supersede {c.lines_supersede} lines / {c.units_supersede} units (wrong BU for {c.target_product_line})
                </Typography>
              ))}
              <Typography variant="body2" sx={{ fontWeight: 600 }}>
                Total lines to soft-supersede: {previewQ.data.total_lines_to_supersede}
              </Typography>
            </Stack>
          ) : null}
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setConfirmOpen(false)}>Cancel</Button>
          <Button
            variant="contained"
            color="warning"
            disabled={applyM.isPending || !previewQ.data?.total_lines_to_supersede}
            onClick={() => applyM.mutate()}
          >
            Apply partition (governed)
          </Button>
        </DialogActions>
      </Dialog>
    </Alert>
  );
}
