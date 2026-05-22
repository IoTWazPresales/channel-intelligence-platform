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
import { GeoStewardRegisterFromFile } from "./GeoStewardRegisterFromFile";
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
  const [rgMapId, setRgMapId] = useState<Record<string, string>>({});

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

  const hintRegionMut = useMutation({
    mutationFn: async (args: { raw_token: string; iso_alpha2?: string }) =>
      apiPost(`/api/v1/mappings/import-jobs/${importJobId}/dsi-geo-steward/region-register-from-hint`, {
        raw_token: args.raw_token,
        iso_alpha2: args.iso_alpha2 ?? null,
        notes: null,
      }),
    onSuccess: () => {
      setMsg('Region registered from geographic hint (not channel→region mapping). Revalidate when ready.');
      invalidateGeo();
    },
  });

  const geoBusy =
    chAliasMut.isPending ||
    chCreateMut.isPending ||
    rgAliasMut.isPending ||
    rgCreateMut.isPending ||
    hintRegionMut.isPending;

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
                {row.geographic_hint ? (
                  <Alert severity="info" variant="outlined" sx={{ mt: 1 }}>
                    Geographic hint (not RTM): {row.geographic_hint.guessed_region_code ?? '—'}
                    {row.geographic_hint.matched_catalog ? ' · catalog match' : ' · no catalog match yet'}
                  </Alert>
                ) : null}
                {row.geographic_hint ? (
                  <Stack direction="row" spacing={1} sx={{ mt: 0.75 }} flexWrap="wrap" useFlexGap>
                    <DsiPendingButton
                      size="small"
                      variant="contained"
                      pending={hintRegionMut.isPending}
                      pendingLabel="Registering…"
                      disabled={geoBusy && !hintRegionMut.isPending}
                      onClick={() =>
                        void hintRegionMut
                          .mutateAsync({
                            raw_token: row.raw_token,
                            iso_alpha2: row.geographic_hint?.guessed_region_code ?? undefined,
                          })
                          .catch(() => {})
                      }
                      data-testid={`dsi-geo-hint-region-${row.normalized_token}`}
                    >
                      Register ISO region from hint
                    </DsiPendingButton>
                  </Stack>
                ) : null}
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
                <GeoStewardRegisterFromFile
                  row={row}
                  dimension="channel"
                  pending={chCreateMut.isPending}
                  geoBusy={geoBusy}
                  testIdPrefix={`dsi-geo-ch-${row.normalized_token}`}
                  onRegister={async ({ raw_token, code, name }) => {
                    await chCreateMut.mutateAsync({
                      raw_token,
                      channel_code: code,
                      channel_name: name,
                    });
                  }}
                />
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
                <GeoStewardRegisterFromFile
                  row={row}
                  dimension="region"
                  pending={rgCreateMut.isPending}
                  geoBusy={geoBusy}
                  testIdPrefix={`dsi-geo-rg-${row.normalized_token}`}
                  onRegister={async ({ raw_token, code, name }) => {
                    await rgCreateMut.mutateAsync({
                      raw_token,
                      region_code: code,
                      region_name: name,
                    });
                  }}
                />
              </Paper>
            );
          })}
        </Stack>
      ) : null}
    </Stack>
  );
}