'use client';

import { Box, Button, Stack, Typography } from '@mui/material';
import { alpha, useTheme } from '@mui/material/styles';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';

import { formatUnits, type ApplyNetRequirementResponse, type NetRequirementResponse } from '@/features/lineup/lineupTypes';
import { apiGet, apiPost } from '@/lib/api';

export function LineupPlanActionBar() {
  const theme = useTheme();
  const qc = useQueryClient();
  const [applyMsg, setApplyMsg] = useState<string | null>(null);
  const [applyPeriodStart, setApplyPeriodStart] = useState('2026-04-01');
  const [applyPeriodLabel, setApplyPeriodLabel] = useState('2026Q2');
  const applyBias = true;

  const { data: netReq, refetch: refetchNetReq, isFetching } = useQuery({
    queryKey: ['lineup-net-requirement', applyBias],
    queryFn: ({ signal }) =>
      apiGet<NetRequirementResponse>(
        `/api/v1/lineup/net-requirement?limit=200&include_customer_shares=false&apply_bias=${applyBias ? 'true' : 'false'}`,
        { signal },
      ),
  });

  const netTotal = Math.round((netReq?.rows ?? []).reduce((s, r) => s + (r.net_requirement || 0), 0));

  const applyNetReq = useMutation({
    mutationFn: () =>
      apiPost<ApplyNetRequirementResponse>('/api/v1/lineup/apply-net-requirement', {
        confirm: true,
        period_start: applyPeriodStart,
        period_label: applyPeriodLabel.trim() || null,
        replace_matching: true,
        limit: 200,
        horizon_weeks: 13,
        apply_bias: applyBias,
        write_commercial_case: true,
      }),
    onSuccess: (res) => {
      setApplyMsg(`Applied: inserted ${res.inserted}, updated ${res.updated}`);
      void qc.invalidateQueries({ queryKey: ['lineup-items'] });
    },
    onError: (err) => setApplyMsg(err instanceof Error ? err.message : String(err)),
  });

  return (
    <Box
      data-testid="lineup-plan-action-bar"
      sx={{
        display: 'flex',
        alignItems: 'center',
        gap: 2,
        px: 2.75,
        py: 1.25,
        borderTop: `1px solid ${alpha(theme.palette.common.white, 0.12)}`,
        bgcolor: '#1a1d23',
        flexWrap: 'wrap',
      }}
    >
      <Typography
        sx={{ fontFamily: '"IBM Plex Mono", monospace', fontSize: '9.5px', letterSpacing: '0.08em', textTransform: 'uppercase', color: alpha(theme.palette.text.primary, 0.45) }}
      >
        Net requirement
      </Typography>
      <Typography sx={{ fontFamily: '"IBM Plex Mono", monospace', fontSize: '12px', color: alpha(theme.palette.text.primary, 0.75) }}>
        {formatUnits(netTotal)} units (B2)
      </Typography>
      {applyMsg ? (
        <Typography sx={{ fontSize: '11px', color: alpha(theme.palette.text.primary, 0.6) }}>{applyMsg}</Typography>
      ) : null}
      <Stack direction="row" spacing={1} sx={{ ml: 'auto' }} flexWrap="wrap" useFlexGap>
        <Button
          size="small"
          data-testid="lineup-net-calc"
          disabled={isFetching}
          onClick={() => void refetchNetReq()}
          sx={{ textTransform: 'none', borderColor: alpha(theme.palette.common.white, 0.2), color: alpha(theme.palette.text.primary, 0.75) }}
          variant="outlined"
        >
          Calc
        </Button>
        <Button
          size="small"
          component="a"
          href={`/api/v1/lineup/net-requirement/export.xlsx?limit=200&apply_bias=true&period_start=${encodeURIComponent(applyPeriodStart)}&period_label=${encodeURIComponent(applyPeriodLabel)}`}
          data-testid="lineup-net-export"
          sx={{ textTransform: 'none', borderColor: alpha(theme.palette.common.white, 0.2), color: alpha(theme.palette.text.primary, 0.75) }}
          variant="outlined"
        >
          Export
        </Button>
        <Button
          size="small"
          variant="contained"
          data-testid="lineup-apply-net-requirement"
          disabled={applyNetReq.isPending || !(netReq?.rows?.length)}
          onClick={() => {
            if (!window.confirm(`Apply net requirement into draft lineup for ${applyPeriodLabel}?`)) return;
            setApplyMsg(null);
            void applyNetReq.mutate();
          }}
          sx={{
            textTransform: 'none',
            fontWeight: 600,
            color: '#bfe8f8',
            bgcolor: alpha('#3db8e8', 0.16),
            border: `1px solid ${alpha('#3db8e8', 0.55)}`,
            boxShadow: 'none',
            '&:hover': { bgcolor: alpha('#3db8e8', 0.22), boxShadow: 'none' },
          }}
        >
          {applyNetReq.isPending ? 'Applying…' : 'Apply'}
        </Button>
      </Stack>
    </Box>
  );
}
