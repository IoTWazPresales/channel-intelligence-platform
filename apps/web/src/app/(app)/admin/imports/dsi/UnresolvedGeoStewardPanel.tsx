'use client';

import { useCallback, useMemo, useState } from 'react';
import {
  Alert,
  Box,
  Button,
  Checkbox,
  Chip,
  Collapse,
  FormControl,
  InputLabel,
  MenuItem,
  Select,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  TextField,
  Typography,
} from '@mui/material';
import { useMutation, useQueryClient } from '@tanstack/react-query';

import { apiPost, safeDisplayError } from '@/lib/api';

import { invalidateDsiCatalogQueries, invalidateDsiImportJobStewardQueries } from './dsiSteward.config';
import { StewardPendingButton } from '@/features/import-steward/StewardPendingButton';
import { prefillGeoCreateFromFileToken } from './geoStewardFilePrefill';
import { GeoStewardRegisterFromFile } from './GeoStewardRegisterFromFile';
import { geoRowHasRegionHint, geoRowIsoHint, geoRowRegionAliasRegistered } from './geoStewardHints';
import type {
  DsiCatalogOpt,
  DsiGeoStewardBulkApplyResponse,
  DsiGeoStewardBulkItem,
  DsiUnresolvedGeoRowDto,
} from './dsiSteward.types';

type GeoRowKind = 'channel' | 'region';

type GeoTableRow = DsiUnresolvedGeoRowDto & { kind: GeoRowKind; rowKey: string };

const DETAIL_COL_SPAN = 6;

function GeoStewardTableRow({
  row,
  kind,
  rowKey,
  selected,
  onToggleSelected,
  catalogOptions,
  mapId,
  onMapIdChange,
  overrideOpen,
  onToggleOverride,
  code,
  name,
  onCodeChange,
  onNameChange,
  geoBusy,
  onSaveAlias,
  aliasPending,
  onRegisterFromFile,
  registerPending,
  onRegisterChannelFromFile,
  onRegisterFromHint,
  hintPending,
  isGeographicChannel,
  regionAliasRegistered,
}: {
  row: DsiUnresolvedGeoRowDto;
  kind: GeoRowKind;
  rowKey: string;
  selected: boolean;
  onToggleSelected: () => void;
  catalogOptions: DsiCatalogOpt[];
  mapId: string;
  onMapIdChange: (value: string) => void;
  overrideOpen: boolean;
  onToggleOverride: () => void;
  code: string;
  name: string;
  onCodeChange: (value: string) => void;
  onNameChange: (value: string) => void;
  geoBusy: boolean;
  onSaveAlias: () => void;
  aliasPending: boolean;
  onRegisterFromFile: () => void;
  registerPending: boolean;
  onRegisterChannelFromFile?: (args: { raw_token: string; code: string; name: string }) => void | Promise<void>;
  onRegisterFromHint?: () => void;
  hintPending?: boolean;
  isGeographicChannel: boolean;
  regionAliasRegistered: boolean;
}) {
  const mapLabel = kind === 'channel' ? 'Map to channel' : 'Map to region';
  const canRegister = Boolean(code.trim() && name.trim());

  return (
    <>
      <TableRow
        data-testid={`dsi-geo-row-${row.normalized_token}`}
        hover
        selected={selected}
        sx={isGeographicChannel ? { bgcolor: 'action.hover' } : undefined}
      >
        <TableCell padding="checkbox" sx={{ verticalAlign: 'top' }}>
          <Checkbox
            size="small"
            checked={selected}
            onChange={onToggleSelected}
            inputProps={{ 'aria-label': `Select ${row.raw_token}` }}
          />
        </TableCell>
        <TableCell sx={{ verticalAlign: 'top', maxWidth: 180 }}>
          <Typography variant="body2" sx={{ wordBreak: 'break-word', fontWeight: 500 }}>
            {row.raw_token}
          </Typography>
          <Stack direction="row" spacing={0.5} flexWrap="wrap" useFlexGap sx={{ mt: 0.5 }}>
            <Typography variant="caption" color="text.secondary">
              {kind === 'channel' ? 'Channel' : 'Region'}
            </Typography>
            {isGeographicChannel ? (
              <Chip label="Geographic" size="small" color="info" variant="outlined" sx={{ height: 20 }} />
            ) : null}
          </Stack>
        </TableCell>
        <TableCell sx={{ verticalAlign: 'top', maxWidth: 160 }}>
          <Typography variant="caption" color="text.secondary" display="block">
            {row.resolution_detail}
          </Typography>
          <Typography variant="caption" display="block">
            {row.row_count} rows
          </Typography>
        </TableCell>
        <TableCell sx={{ verticalAlign: 'top', minWidth: 160 }}>
          {isGeographicChannel ? (
            <Stack spacing={0.5}>
              <Typography variant="caption" display="block">
                Region: {geoRowIsoHint(row) ?? '—'}
              </Typography>
              <Typography variant="caption" color="text.secondary" display="block">
                {regionAliasRegistered
                  ? 'Region alias registered for this file token'
                  : row.geographic_hint?.matched_catalog
                    ? 'ISO region in catalog — register alias to link token'
                    : 'Create/link region alias'}
              </Typography>
              {regionAliasRegistered ? (
                <Chip label="Registered" size="small" color="success" variant="outlined" sx={{ height: 22 }} />
              ) : onRegisterFromHint ? (
                <StewardPendingButton
                  size="small"
                  variant="contained"
                  pending={Boolean(hintPending)}
                  pendingLabel="Registering…"
                  disabled={geoBusy && !hintPending}
                  onClick={() => void onRegisterFromHint()}
                  data-testid={`dsi-geo-hint-region-${row.normalized_token}`}
                >
                  Register ISO region
                </StewardPendingButton>
              ) : null}
            </Stack>
          ) : (
            <Typography variant="caption" color="text.secondary">
              —
            </Typography>
          )}
        </TableCell>
        <TableCell sx={{ verticalAlign: 'top', minWidth: 200 }}>
          <Stack direction="row" spacing={0.75} alignItems="center" flexWrap="wrap" useFlexGap>
            <FormControl size="small" sx={{ minWidth: 160, flex: '1 1 140px' }}>
              <InputLabel id={`${rowKey}-map`}>{mapLabel}</InputLabel>
              <Select
                labelId={`${rowKey}-map`}
                label={mapLabel}
                value={mapId}
                onChange={(e) => onMapIdChange(String(e.target.value))}
              >
                <MenuItem value="">
                  <em>Select…</em>
                </MenuItem>
                {catalogOptions.map((opt) => (
                  <MenuItem key={opt.id} value={String(opt.id)}>
                    {opt.code} — {opt.name}
                  </MenuItem>
                ))}
              </Select>
            </FormControl>
            <StewardPendingButton
              size="small"
              variant="outlined"
              pending={aliasPending}
              pendingLabel="Saving…"
              disabled={(geoBusy && !aliasPending) || !mapId.trim()}
              onClick={() => void onSaveAlias()}
              data-testid={`dsi-geo-${kind === 'channel' ? 'ch' : 'rg'}-alias-${row.normalized_token}`}
            >
              Save alias
            </StewardPendingButton>
          </Stack>
        </TableCell>
        <TableCell sx={{ verticalAlign: 'top', minWidth: 200 }}>
          {!isGeographicChannel ? (
            <>
              <Typography variant="caption" color="text.secondary" display="block" sx={{ mb: 0.5 }}>
                {code} — {name}
              </Typography>
              <Stack direction="row" spacing={0.75} alignItems="center" flexWrap="wrap" useFlexGap>
                <StewardPendingButton
                  size="small"
                  variant="contained"
                  pending={registerPending}
                  pendingLabel="Registering…"
                  disabled={(geoBusy && !registerPending) || !canRegister}
                  onClick={() => void onRegisterFromFile()}
                  data-testid={`dsi-geo-${kind === 'channel' ? 'ch' : 'rg'}-${row.normalized_token}-register-btn`}
                >
                  Register from file
                </StewardPendingButton>
                <Typography
                  component="button"
                  type="button"
                  variant="caption"
                  color="primary"
                  onClick={onToggleOverride}
                  sx={{
                    border: 0,
                    bgcolor: 'transparent',
                    cursor: 'pointer',
                    p: 0,
                    textDecoration: 'underline',
                  }}
                >
                  {overrideOpen ? 'Hide override' : 'Override code/name'}
                </Typography>
              </Stack>
            </>
          ) : (
            <Stack spacing={0.75}>
              <Typography variant="caption" color="text.secondary" display="block">
                {regionAliasRegistered
                  ? 'ISO region alias saved. Re-run validation to refresh the customer plan.'
                  : 'Primary path: register as ISO region (left). These values sit in the file Channel column but encode countries, not RTM routes like Mass Retail.'}
              </Typography>
              <GeoStewardRegisterFromFile
                row={row}
                dimension="channel"
                pending={registerPending}
                geoBusy={geoBusy}
                onRegister={async (args) => {
                  if (onRegisterChannelFromFile) {
                    await onRegisterChannelFromFile(args);
                  }
                }}
                testIdPrefix={`dsi-geo-ch-rtm-${row.normalized_token}`}
              />
            </Stack>
          )}
        </TableCell>
      </TableRow>
      {!isGeographicChannel ? (
        <TableRow>
          <TableCell colSpan={DETAIL_COL_SPAN} sx={{ py: 0, borderBottom: overrideOpen ? undefined : 0 }}>
            <Collapse in={overrideOpen} unmountOnExit>
              <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1} sx={{ py: 1.5 }}>
                <TextField
                  size="small"
                  label={kind === 'channel' ? 'Channel code' : 'Region code'}
                  value={code}
                  onChange={(e) => onCodeChange(e.target.value)}
                  inputProps={{
                    'data-testid': `dsi-geo-${kind === 'channel' ? 'ch' : 'rg'}-${row.normalized_token}-code`,
                  }}
                />
                <TextField
                  size="small"
                  label={kind === 'channel' ? 'Channel name' : 'Region name'}
                  value={name}
                  onChange={(e) => onNameChange(e.target.value)}
                  inputProps={{
                    'data-testid': `dsi-geo-${kind === 'channel' ? 'ch' : 'rg'}-${row.normalized_token}-name`,
                  }}
                />
              </Stack>
            </Collapse>
          </TableCell>
        </TableRow>
      ) : null}
    </>
  );
}

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
  const [bulkSummary, setBulkSummary] = useState<string | null>(null);
  const [selectedKeys, setSelectedKeys] = useState<Set<string>>(new Set());
  const [chMapId, setChMapId] = useState<Record<string, string>>({});
  const [rgMapId, setRgMapId] = useState<Record<string, string>>({});
  const [overrideOpen, setOverrideOpen] = useState<Record<string, boolean>>({});
  const [draftCode, setDraftCode] = useState<Record<string, string>>({});
  const [draftName, setDraftName] = useState<Record<string, string>>({});

  const tableRows = useMemo((): GeoTableRow[] => {
    const out: GeoTableRow[] = [];
    for (const row of channels) {
      out.push({ ...row, kind: 'channel', rowKey: `ch:${row.normalized_token}` });
    }
    for (const row of regions) {
      out.push({ ...row, kind: 'region', rowKey: `rg:${row.normalized_token}` });
    }
    return out.sort((a, b) => {
      if (a.kind !== b.kind) return a.kind === 'channel' ? -1 : 1;
      return a.normalized_token.localeCompare(b.normalized_token);
    });
  }, [channels, regions]);

  const selectedRows = useMemo(
    () => tableRows.filter((row) => selectedKeys.has(row.rowKey)),
    [selectedKeys, tableRows]
  );

  const geographicChannelRows = useMemo(
    () =>
      selectedRows.filter(
        (row) => row.kind === 'channel' && geoRowHasRegionHint(row) && !geoRowRegionAliasRegistered(row)
      ),
    [selectedRows]
  );

  const registerFromFileRows = useMemo(
    () => selectedRows.filter((row) => row.kind === 'channel' || row.kind === 'region'),
    [selectedRows]
  );

  const prefillFor = useCallback(
    (row: GeoTableRow) => {
      const existingCode = draftCode[row.rowKey];
      const existingName = draftName[row.rowKey];
      if (existingCode != null && existingName != null) {
        return { code: existingCode, name: existingName };
      }
      return prefillGeoCreateFromFileToken(row.raw_token, row.normalized_token, row.kind);
    },
    [draftCode, draftName]
  );

  const invalidateGeo = useCallback(() => {
    invalidateDsiImportJobStewardQueries(qc, importJobId);
    invalidateDsiCatalogQueries(qc);
    onInvalidate();
  }, [importJobId, onInvalidate, qc]);

  const bulkApplyMut = useMutation({
    mutationFn: async (body: { action: 'register_region_from_hint' | 'register_from_file'; items: DsiGeoStewardBulkItem[] }) =>
      apiPost<DsiGeoStewardBulkApplyResponse>(
        `/api/v1/mappings/import-jobs/${importJobId}/dsi-geo-steward/bulk-apply`,
        body
      ),
    onSuccess: (data) => {
      setBulkSummary(`Bulk ${data.action}: ${data.applied} applied, ${data.failed} failed.`);
      if (data.failed === 0) {
        setMsg('Bulk geo stewardship complete. Re-run validation when ready.');
      } else {
        setMsg(`Bulk completed with ${data.failed} failure(s). Successful rows were saved.`);
      }
      setSelectedKeys(new Set());
      invalidateGeo();
    },
  });

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
    bulkApplyMut.isPending ||
    chAliasMut.isPending ||
    chCreateMut.isPending ||
    rgAliasMut.isPending ||
    rgCreateMut.isPending ||
    hintRegionMut.isPending;

  const allSelected = tableRows.length > 0 && selectedKeys.size === tableRows.length;
  const someSelected = selectedKeys.size > 0 && !allSelected;

  const toggleAll = () => {
    if (allSelected) {
      setSelectedKeys(new Set());
    } else {
      setSelectedKeys(new Set(tableRows.map((row) => row.rowKey)));
    }
  };

  const runBulkRegionHints = () => {
    if (geographicChannelRows.length === 0) return;
    const items: DsiGeoStewardBulkItem[] = geographicChannelRows.map((row) => ({
      kind: 'channel',
      raw_token: row.raw_token,
      normalized_token: row.normalized_token,
      iso_alpha2: geoRowIsoHint(row),
    }));
    void bulkApplyMut.mutateAsync({ action: 'register_region_from_hint', items }).catch(() => {});
  };

  const runBulkRegisterFromFile = () => {
    if (registerFromFileRows.length === 0) return;
    const items: DsiGeoStewardBulkItem[] = registerFromFileRows.map((row) => {
      const prefill = prefillFor(row);
      const code = (draftCode[row.rowKey] ?? prefill.code).trim();
      const name = (draftName[row.rowKey] ?? prefill.name).trim();
      return {
        kind: row.kind,
        raw_token: row.raw_token,
        normalized_token: row.normalized_token,
        code,
        name,
      };
    });
    void bulkApplyMut.mutateAsync({ action: 'register_from_file', items }).catch(() => {});
  };

  if (channels.length === 0 && regions.length === 0) {
    return (
      <Typography variant="body2" color="text.secondary" data-testid="dsi-unresolved-geo-empty">
        No unresolved route-to-market or region/province tokens detected for this import under current catalog rules.
      </Typography>
    );
  }

  return (
    <Stack spacing={1.5} data-testid="dsi-unresolved-geo-steward">
      {msg ? (
        <Alert severity="success" onClose={() => setMsg(null)}>
          {msg}
        </Alert>
      ) : null}
      {bulkSummary ? (
        <Alert severity="info" onClose={() => setBulkSummary(null)} data-testid="dsi-geo-bulk-summary">
          {bulkSummary}
        </Alert>
      ) : null}
      {(bulkApplyMut.isError ||
        chAliasMut.isError ||
        chCreateMut.isError ||
        rgAliasMut.isError ||
        rgCreateMut.isError ||
        hintRegionMut.isError) && (
        <Alert severity="error">
          {safeDisplayError(
            bulkApplyMut.error ||
              chAliasMut.error ||
              chCreateMut.error ||
              rgAliasMut.error ||
              rgCreateMut.error ||
              hintRegionMut.error
          )}
        </Alert>
      )}

      <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap" useFlexGap data-testid="dsi-geo-bulk-toolbar">
        <Typography variant="caption" color="text.secondary">
          {selectedKeys.size} selected
        </Typography>
        <Button size="small" variant="text" onClick={toggleAll} disabled={geoBusy || tableRows.length === 0}>
          {allSelected ? 'Deselect all' : 'Select all'}
        </Button>
        <StewardPendingButton
          size="small"
          variant="contained"
          pending={bulkApplyMut.isPending}
          pendingLabel="Applying…"
          disabled={geoBusy && !bulkApplyMut.isPending || geographicChannelRows.length === 0}
          onClick={runBulkRegionHints}
          data-testid="dsi-geo-bulk-register-regions"
        >
          Register ISO regions ({geographicChannelRows.length})
        </StewardPendingButton>
        <StewardPendingButton
          size="small"
          variant="outlined"
          pending={bulkApplyMut.isPending}
          pendingLabel="Applying…"
          disabled={geoBusy && !bulkApplyMut.isPending || registerFromFileRows.length === 0}
          onClick={runBulkRegisterFromFile}
          data-testid="dsi-geo-bulk-register-from-file"
        >
          Register from file ({registerFromFileRows.length})
        </StewardPendingButton>
        <Typography variant="caption" color="text.secondary">
          Geographic tokens: bulk ISO region (left) or bulk channel create (Register from file). Per-row
          actions work the same.
        </Typography>
      </Stack>

      <Box sx={{ overflowX: 'auto' }}>
        <TableContainer data-testid="dsi-unresolved-geo-table">
          <Table size="small" stickyHeader sx={{ minWidth: 980 }}>
            <TableHead>
              <TableRow>
                <TableCell padding="checkbox">
                  <Checkbox
                    size="small"
                    indeterminate={someSelected}
                    checked={allSelected}
                    onChange={toggleAll}
                    inputProps={{ 'aria-label': 'Select all geo tokens' }}
                  />
                </TableCell>
                <TableCell>File token</TableCell>
                <TableCell>Detail</TableCell>
                <TableCell>Geographic hint</TableCell>
                <TableCell>Map to catalog</TableCell>
                <TableCell>Register from file</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {tableRows.map((row) => {
                const prefill = prefillFor(row);
                const code = draftCode[row.rowKey] ?? prefill.code;
                const name = draftName[row.rowKey] ?? prefill.name;
                const mapRecord = row.kind === 'channel' ? chMapId : rgMapId;
                const mapId = mapRecord[row.rowKey] ?? '';
                const isGeographicChannel = row.kind === 'channel' && geoRowHasRegionHint(row);
                const regionAliasRegistered = geoRowRegionAliasRegistered(row);

                return (
                  <GeoStewardTableRow
                    key={row.rowKey}
                    row={row}
                    kind={row.kind}
                    rowKey={row.rowKey}
                    selected={selectedKeys.has(row.rowKey)}
                    onToggleSelected={() =>
                      setSelectedKeys((prev) => {
                        const next = new Set(prev);
                        if (next.has(row.rowKey)) next.delete(row.rowKey);
                        else next.add(row.rowKey);
                        return next;
                      })
                    }
                    catalogOptions={row.kind === 'channel' ? catalogChannels : catalogRegions}
                    mapId={mapId}
                    onMapIdChange={(value) => {
                      if (row.kind === 'channel') {
                        setChMapId((m) => ({ ...m, [row.rowKey]: value }));
                      } else {
                        setRgMapId((m) => ({ ...m, [row.rowKey]: value }));
                      }
                    }}
                    overrideOpen={Boolean(overrideOpen[row.rowKey])}
                    onToggleOverride={() =>
                      setOverrideOpen((m) => ({ ...m, [row.rowKey]: !m[row.rowKey] }))
                    }
                    code={code}
                    name={name}
                    onCodeChange={(value) => setDraftCode((m) => ({ ...m, [row.rowKey]: value }))}
                    onNameChange={(value) => setDraftName((m) => ({ ...m, [row.rowKey]: value }))}
                    geoBusy={geoBusy}
                    isGeographicChannel={isGeographicChannel}
                    regionAliasRegistered={regionAliasRegistered}
                    aliasPending={row.kind === 'channel' ? chAliasMut.isPending : rgAliasMut.isPending}
                    onSaveAlias={() => {
                      const id = Number(mapId);
                      if (!Number.isFinite(id)) return;
                      if (row.kind === 'channel') {
                        void chAliasMut.mutateAsync({ raw_token: row.raw_token, channel_id: id }).catch(() => {});
                      } else {
                        void rgAliasMut.mutateAsync({ raw_token: row.raw_token, region_id: id }).catch(() => {});
                      }
                    }}
                    registerPending={row.kind === 'channel' ? chCreateMut.isPending : rgCreateMut.isPending}
                    onRegisterFromFile={() => {
                      const payload = {
                        raw_token: row.raw_token,
                        code: code.trim(),
                        name: name.trim(),
                      };
                      if (row.kind === 'channel') {
                        void chCreateMut
                          .mutateAsync({
                            raw_token: payload.raw_token,
                            channel_code: payload.code,
                            channel_name: payload.name,
                          })
                          .catch(() => {});
                      } else {
                        void rgCreateMut
                          .mutateAsync({
                            raw_token: payload.raw_token,
                            region_code: payload.code,
                            region_name: payload.name,
                          })
                          .catch(() => {});
                      }
                    }}
                    onRegisterChannelFromFile={(args) => {
                      void chCreateMut.mutateAsync({
                        raw_token: args.raw_token,
                        channel_code: args.code,
                        channel_name: args.name,
                      });
                    }}
                    onRegisterFromHint={
                      isGeographicChannel && !regionAliasRegistered
                        ? () =>
                            void hintRegionMut
                              .mutateAsync({
                                raw_token: row.raw_token,
                                iso_alpha2: geoRowIsoHint(row) ?? undefined,
                              })
                              .catch(() => {})
                        : undefined
                    }
                    hintPending={hintRegionMut.isPending}
                  />
                );
              })}
            </TableBody>
          </Table>
        </TableContainer>
      </Box>
    </Stack>
  );
}
