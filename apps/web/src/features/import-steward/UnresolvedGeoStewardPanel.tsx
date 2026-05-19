"use client";

import { useCallback, useState } from "react";
import {
  Alert,
  Divider,
  FormControl,
  InputLabel,
  MenuItem,
  Paper,
  Select,
  Stack,
  TextField,
  Typography,
} from "@mui/material";
import { useMutation, useQueryClient } from "@tanstack/react-query";

import { apiPost, safeDisplayError } from "@/lib/api";

import { DSI_STEWARD_CONFIG, invalidateDsiCatalogQueries, invalidateDsiImportJobStewardQueries } from "./dsiSteward.config";
import { DsiPendingButton } from "./DsiPendingButton";
import type { DsiCatalogOpt, DsiUnresolvedGeoRowDto } from "./dsiSteward.types";

export function UnresolvedGeoStewardPanel({
  importJobId,
  channels,
  regions,
  catalogChannels,
  catalogRegions,
  onInvalidate,
}: {
  importJobId: number;
  channels: DsiUnresolvedGeoRowDto[];
  regions: DsiUnresolvedGeoRowDto[];
  catalogChannels: DsiCatalogOpt[];
  catalogRegions: DsiCatalogOpt[];
  onInvalidate: () => void;
}) {
  const qc = useQueryClient();
  const [msg, setMsg] = useState<string | null>(null);
  const [chMapId, setChMapId] = useState<Record<string, string>>({});
  const [chNewCode, setChNewCode] = useState<Record<string, string>>({});
  const [chNewName, setChNewName] = useState<Record<string, string>>({});
  const [rgMapId, setRgMapId] = useState<Record<string, string>>({});
  const [rgNewCode, setRgNewCode] = useState<Record<string, string>>({});
  const [rgNewName, setRgNewName] = useState<Record<string, string>>({});

  const invalidateGeo = useCallback(() => {
    invalidateDsiImportJobStewardQueries(qc, importJobId);
    invalidateDsiCatalogQueries(qc);
    onInvalidate();
  }, [importJobId, onInvalidate, qc]);

  const chAliasMut = useMutation({
    mutationFn: async (args: { raw_token: string; channel_id: number }) =>
      apiPost(`/api/v1/mappings/import-jobs/${importJobId}/dsi-geo-steward/channel-alias`, {
        channel_id: args.channel_id,
        raw_token: args.raw_token,
        notes: null,
      }),
    onSuccess: () => {
      setMsg('Channel alias saved. Refresh suggestions or re-run validation to update the plan.');
      invalidateGeo();
    },
  });

  const chCreateMut = useMutation({
    mutationFn: async (args: { raw_token: string; channel_code: string; channel_name: string }) =>
      apiPost(`/api/v1/mappings/import-jobs/${importJobId}/dsi-geo-steward/channel-create`, {
        raw_token: args.raw_token,
        channel_code: args.channel_code,
        channel_name: args.channel_name,
        notes: null,
      }),
    onSuccess: () => {
      setMsg('New governed channel + alias saved. Refresh suggestions or re-run validation.');
      invalidateGeo();
    },
  });

  const rgAliasMut = useMutation({
    mutationFn: async (args: { raw_token: string; region_id: number }) =>
      apiPost(`/api/v1/mappings/import-jobs/${importJobId}/dsi-geo-steward/region-alias`, {
        region_id: args.region_id,
        raw_token: args.raw_token,
        notes: null,
      }),
    onSuccess: () => {
      setMsg('Region alias saved. Refresh suggestions or re-run validation.');
      invalidateGeo();
    },
  });

  const rgCreateMut = useMutation({
    mutationFn: async (args: { raw_token: string; region_code: string; region_name: string }) =>
      apiPost(`/api/v1/mappings/import-jobs/${importJobId}/dsi-geo-steward/region-create`, {
        raw_token: args.raw_token,
        region_code: args.region_code,
        region_name: args.region_name,
        notes: null,
      }),
    onSuccess: () => {
      setMsg('New governed region + alias saved. Refresh suggestions or re-run validation.');
      invalidateGeo();
    },
  });

  const geoBusy =
    chAliasMut.isPending || chCreateMut.isPending || rgAliasMut.isPending || rgCreateMut.isPending;

  if (channels.length === 0 && regions.length === 0) {
    return (
      <Typography variant="body2" color="text.secondary" data-testid="dsi-unresolved-geo-empty">
        No unresolved route-to-market or region/province tokens detected for this import under current catalog rules.
      </Typography>
    );
  }

  return (
    <Stack spacing={2} data-testid="dsi-unresolved-geo-steward">
      {msg ? (
        <Alert severity="success" onClose={() => setMsg(null)}>
          {msg}
        </Alert>
      ) : null}
      {(chAliasMut.isError || chCreateMut.isError || rgAliasMut.isError || rgCreateMut.isError) && (
        <Alert severity="error">
          {safeDisplayError(chAliasMut.error || chCreateMut.error || rgAliasMut.error || rgCreateMut.error)}
        </Alert>
      )}
      {channels.length ? (
        <Stack spacing={1.5}>
          <Typography variant="subtitle2">Unresolved route-to-market / channel (file evidence)</Typography>
          {channels.map((row) => {
            const k = `ch:${row.normalized_token}`;
            return (
              <Paper key={k} variant="outlined" sx={{ p: 1.5 }}>
                <Typography variant="body2" sx={{ wordBreak: 'break-word' }}>
                  <strong>Raw:</strong> {row.raw_token}
                </Typography>
                <Typography variant="caption" color="text.secondary" display="block">
                  Detail: {row.resolution_detail} · rows in file (candidates): {row.row_count}
                </Typography>
                <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1} sx={{ mt: 1 }} alignItems={{ sm: 'center' }}>
                  <FormControl size="small" sx={{ minWidth: 200 }}>
                    <InputLabel id={`${k}-map`}>Map to existing channel</InputLabel>
                    <Select
                      labelId={`${k}-map`}
                      label="Map to existing channel"
                      value={chMapId[k] ?? ''}
                      onChange={(e) => setChMapId((m) => ({ ...m, [k]: String(e.target.value) }))}
                    >
                      <MenuItem value="">
                        <em>Select…</em>
                      </MenuItem>
                      {catalogChannels.map((c) => (
                        <MenuItem key={c.id} value={String(c.id)}>
                          {c.code} — {c.name}
                        </MenuItem>
                      ))}
                    </Select>
                  </FormControl>
                  <DsiPendingButton
                    size="small"
                    variant="outlined"
                    pending={chAliasMut.isPending}
                    pendingLabel="Saving…"
                    disabled={(geoBusy && !chAliasMut.isPending) || !(chMapId[k] || '').trim()}
                    onClick={() => {
                      const id = Number(chMapId[k]);
                      if (!Number.isFinite(id)) return;
                      void chAliasMut.mutateAsync({ raw_token: row.raw_token, channel_id: id }).catch(() => {});
                    }}
                    data-testid={`dsi-geo-ch-alias-${row.normalized_token}`}
                  >
                    Save alias
                  </DsiPendingButton>
                </Stack>
                <Divider sx={{ my: 1 }} />
                <Typography variant="caption" color="text.secondary">
                  Or create a new governed channel (distinct RTM stays distinct)
                </Typography>
                <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1} sx={{ mt: 0.75 }}>
                  <TextField
                    size="small"
                    label="New channel code"
                    value={chNewCode[k] ?? ''}
                    onChange={(e) => setChNewCode((m) => ({ ...m, [k]: e.target.value }))}
                    inputProps={{ 'data-testid': `dsi-geo-ch-code-${row.normalized_token}` }}
                  />
                  <TextField
                    size="small"
                    label="New channel name"
                    value={chNewName[k] ?? ''}
                    onChange={(e) => setChNewName((m) => ({ ...m, [k]: e.target.value }))}
                    inputProps={{ 'data-testid': `dsi-geo-ch-name-${row.normalized_token}` }}
                  />
                  <DsiPendingButton
                    size="small"
                    variant="contained"
                    pending={chCreateMut.isPending}
                    pendingLabel="Creating…"
                    disabled={
                      (geoBusy && !chCreateMut.isPending) ||
                      !(chNewCode[k] || '').trim() ||
                      !(chNewName[k] || '').trim()
                    }
                    onClick={() =>
                      void chCreateMut
                        .mutateAsync({
                          raw_token: row.raw_token,
                          channel_code: (chNewCode[k] || '').trim(),
                          channel_name: (chNewName[k] || '').trim(),
                        })
                        .catch(() => {})
                    }
                    data-testid={`dsi-geo-ch-create-${row.normalized_token}`}
                  >
                    Create + map
                  </DsiPendingButton>
                </Stack>
              </Paper>
            );
          })}
        </Stack>
      ) : null}
      {regions.length ? (
        <Stack spacing={1.5}>
          <Typography variant="subtitle2">Unresolved region / province (file evidence)</Typography>
          {regions.map((row) => {
            const k = `rg:${row.normalized_token}`;
            return (
              <Paper key={k} variant="outlined" sx={{ p: 1.5 }}>
                <Typography variant="body2" sx={{ wordBreak: 'break-word' }}>
                  <strong>Raw:</strong> {row.raw_token}
                </Typography>
                <Typography variant="caption" color="text.secondary" display="block">
                  Detail: {row.resolution_detail} · rows in file (candidates): {row.row_count}
                </Typography>
                <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1} sx={{ mt: 1 }} alignItems={{ sm: 'center' }}>
                  <FormControl size="small" sx={{ minWidth: 200 }}>
                    <InputLabel id={`${k}-map`}>Map to existing region</InputLabel>
                    <Select
                      labelId={`${k}-map`}
                      label="Map to existing region"
                      value={rgMapId[k] ?? ''}
                      onChange={(e) => setRgMapId((m) => ({ ...m, [k]: String(e.target.value) }))}
                    >
                      <MenuItem value="">
                        <em>Select…</em>
                      </MenuItem>
                      {catalogRegions.map((r) => (
                        <MenuItem key={r.id} value={String(r.id)}>
                          {r.code} — {r.name}
                        </MenuItem>
                      ))}
                    </Select>
                  </FormControl>
                  <DsiPendingButton
                    size="small"
                    variant="outlined"
                    pending={rgAliasMut.isPending}
                    pendingLabel="Saving…"
                    disabled={(geoBusy && !rgAliasMut.isPending) || !(rgMapId[k] || '').trim()}
                    onClick={() => {
                      const id = Number(rgMapId[k]);
                      if (!Number.isFinite(id)) return;
                      void rgAliasMut.mutateAsync({ raw_token: row.raw_token, region_id: id }).catch(() => {});
                    }}
                    data-testid={`dsi-geo-rg-alias-${row.normalized_token}`}
                  >
                    Save alias
                  </DsiPendingButton>
                </Stack>
                <Divider sx={{ my: 1 }} />
                <Typography variant="caption" color="text.secondary">
                  Or create a new governed region
                </Typography>
                <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1} sx={{ mt: 0.75 }}>
                  <TextField
                    size="small"
                    label="New region code"
                    value={rgNewCode[k] ?? ''}
                    onChange={(e) => setRgNewCode((m) => ({ ...m, [k]: e.target.value }))}
                    inputProps={{ 'data-testid': `dsi-geo-rg-code-${row.normalized_token}` }}
                  />
                  <TextField
                    size="small"
                    label="New region name"
                    value={rgNewName[k] ?? ''}
                    onChange={(e) => setRgNewName((m) => ({ ...m, [k]: e.target.value }))}
                    inputProps={{ 'data-testid': `dsi-geo-rg-name-${row.normalized_token}` }}
                  />
                  <DsiPendingButton
                    size="small"
                    variant="contained"
                    pending={rgCreateMut.isPending}
                    pendingLabel="Creating…"
                    disabled={
                      (geoBusy && !rgCreateMut.isPending) ||
                      !(rgNewCode[k] || '').trim() ||
                      !(rgNewName[k] || '').trim()
                    }
                    onClick={() =>
                      void rgCreateMut
                        .mutateAsync({
                          raw_token: row.raw_token,
                          region_code: (rgNewCode[k] || '').trim(),
                          region_name: (rgNewName[k] || '').trim(),
                        })
                        .catch(() => {})
                    }
                    data-testid={`dsi-geo-rg-create-${row.normalized_token}`}
                  >
                    Create + map
                  </DsiPendingButton>
                </Stack>
              </Paper>
            );
          })}
        </Stack>
      ) : null}
    </Stack>
  );
}