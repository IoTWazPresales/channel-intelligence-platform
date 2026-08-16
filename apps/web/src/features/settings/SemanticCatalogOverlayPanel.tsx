'use client';

import {
  Alert,
  Box,
  Button,
  Checkbox,
  Divider,
  FormControl,
  FormControlLabel,
  InputLabel,
  MenuItem,
  Select,
  Stack,
  Switch,
  TextField,
  Typography,
} from '@mui/material';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useEffect, useMemo, useState } from 'react';

import { apiGet, apiPut, safeDisplayError } from '@/lib/api';

type GrainSet = string[];

type BaseMetric = {
  id: string;
  key: string;
  label: string;
  allowed_grains: GrainSet[];
  fact_family: string | null;
  handler_backed: boolean;
  locked: { formula: string; source_facts: string[]; owner_surface: string };
};

type OverlayPatch = { label?: string; hidden?: boolean; allowed_grains?: GrainSet[] };

type ComposedDraft = {
  key: string;
  label: string;
  op: 'ratio' | 'alias';
  inputs: string[];
  grain: GrainSet;
};

type OverlayEditorPayload = {
  tenant_id: string;
  overlay: { metrics?: Record<string, OverlayPatch>; composed?: Record<string, unknown> };
  base_metrics: BaseMetric[];
  compose_ops: Array<'ratio' | 'alias'>;
};

const OVERLAY_QUERY_KEY = ['semantics', 'overlay'] as const;
const CATALOG_QUERY_KEY = ['semantics', 'catalog'] as const;

function grainToken(set: GrainSet): string {
  return [...set].map((d) => d.trim().toLowerCase()).filter(Boolean).sort().join(',');
}

function parseGrainToken(token: string): GrainSet {
  return token.split(',').map((d) => d.trim()).filter(Boolean);
}

function sameSets(a: GrainSet[], b: GrainSet[]): boolean {
  const left = new Set(a.map(grainToken));
  const right = new Set(b.map(grainToken));
  if (left.size !== right.size) return false;
  for (const t of left) if (!right.has(t)) return false;
  return true;
}

function intersectGrainSets(sets: GrainSet[][]): GrainSet[] {
  if (!sets.length) return [];
  const [first, ...rest] = sets;
  return first.filter((candidate) =>
    rest.every((group) => group.some((g) => grainToken(g) === grainToken(candidate)))
  );
}

function composedFromOverlay(raw: Record<string, unknown> | undefined): ComposedDraft[] {
  if (!raw) return [];
  const out: ComposedDraft[] = [];
  for (const [ident, body] of Object.entries(raw)) {
    if (!body || typeof body !== 'object') continue;
    const row = body as {
      key?: string;
      label?: string;
      compose?: { op?: string; inputs?: string[]; grain?: GrainSet };
    };
    const op = row.compose?.op === 'alias' ? 'alias' : 'ratio';
    const inputs = Array.isArray(row.compose?.inputs) ? row.compose.inputs.map(String) : [];
    out.push({
      key: String(row.key || ident),
      label: String(row.label || ident),
      op,
      inputs: op === 'alias' ? inputs.slice(0, 1) : inputs.slice(0, 2),
      grain: Array.isArray(row.compose?.grain) ? row.compose.grain.map(String) : [],
    });
  }
  return out;
}

export function SemanticCatalogOverlayPanel() {
  const qc = useQueryClient();
  const overlayQuery = useQuery({
    queryKey: OVERLAY_QUERY_KEY,
    queryFn: () => apiGet<OverlayEditorPayload>('/api/v1/semantics/overlay'),
    staleTime: 15_000,
  });

  const [labels, setLabels] = useState<Record<string, string>>({});
  const [hidden, setHidden] = useState<Record<string, boolean>>({});
  const [grainTokens, setGrainTokens] = useState<Record<string, string[]>>({});
  const [composed, setComposed] = useState<ComposedDraft[]>([]);
  const [saveOk, setSaveOk] = useState<string | null>(null);
  const [saveError, setSaveError] = useState<string | null>(null);

  const baseMetrics = overlayQuery.data?.base_metrics ?? [];
  const byKey = useMemo(() => {
    const map = new Map<string, BaseMetric>();
    for (const m of baseMetrics) map.set(m.key, m);
    return map;
  }, [baseMetrics]);

  useEffect(() => {
    const data = overlayQuery.data;
    if (!data) return;
    const nextLabels: Record<string, string> = {};
    const nextHidden: Record<string, boolean> = {};
    const nextGrains: Record<string, string[]> = {};
    const patches = data.overlay.metrics || {};
    for (const m of data.base_metrics) {
      const patch = patches[m.key] || patches[m.id] || {};
      nextLabels[m.key] = typeof patch.label === 'string' && patch.label.trim() ? patch.label : m.label;
      nextHidden[m.key] = Boolean(patch.hidden);
      const selected = Array.isArray(patch.allowed_grains) && patch.allowed_grains.length
        ? patch.allowed_grains.map(grainToken)
        : m.allowed_grains.map(grainToken);
      nextGrains[m.key] = selected;
    }
    setLabels(nextLabels);
    setHidden(nextHidden);
    setGrainTokens(nextGrains);
    setComposed(composedFromOverlay(data.overlay.composed as Record<string, unknown> | undefined));
  }, [overlayQuery.data]);

  const handlerBacked = useMemo(
    () => baseMetrics.filter((m) => m.handler_backed && m.fact_family),
    [baseMetrics]
  );

  const mutation = useMutation({
    mutationFn: () => {
      const metrics: Record<string, OverlayPatch> = {};
      for (const m of baseMetrics) {
        const patch: OverlayPatch = {};
        const label = (labels[m.key] || '').trim();
        if (label && label !== m.label) patch.label = label;
        if (hidden[m.key]) patch.hidden = true;
        const selected = (grainTokens[m.key] || []).map(parseGrainToken).filter((g) => g.length);
        if (selected.length && !sameSets(selected, m.allowed_grains)) {
          patch.allowed_grains = selected;
        }
        if (Object.keys(patch).length) metrics[m.key] = patch;
      }
      const composedPayload: Record<string, unknown> = {};
      for (const row of composed) {
        const key = row.key.trim().toLowerCase();
        if (!key || !row.label.trim()) continue;
        const inputs = row.op === 'alias' ? row.inputs.slice(0, 1) : row.inputs.slice(0, 2);
        composedPayload[key] = {
          key,
          label: row.label.trim(),
          compose: { op: row.op, inputs, grain: row.grain },
        };
      }
      return apiPut<OverlayEditorPayload>('/api/v1/semantics/overlay', {
        metrics,
        composed: composedPayload,
      });
    },
    onSuccess: async (data) => {
      setSaveError(null);
      setSaveOk('Saved. Catalog and queries now use this overlay.');
      qc.setQueryData(OVERLAY_QUERY_KEY, data);
      await qc.invalidateQueries({ queryKey: CATALOG_QUERY_KEY });
      await qc.invalidateQueries({ queryKey: ['semantics-catalog'] });
      await qc.invalidateQueries({ queryKey: ['auth', 'tenant-commercial-profile'] });
    },
    onError: (err) => {
      setSaveOk(null);
      setSaveError(safeDisplayError(err));
    },
  });

  function addComposed() {
    const first = handlerBacked[0];
    const second = handlerBacked.find((m) => m.fact_family === first?.fact_family && m.key !== first?.key);
    const grain = first?.allowed_grains[0] || ['period'];
    setComposed((rows) => [
      ...rows,
      {
        key: `custom_metric_${rows.length + 1}`,
        label: 'Custom metric',
        op: 'ratio',
        inputs: [first?.key || '', second?.key || first?.key || ''].filter(Boolean),
        grain,
      },
    ]);
  }

  function updateComposed(index: number, patch: Partial<ComposedDraft>) {
    setComposed((rows) => rows.map((row, i) => (i === index ? { ...row, ...patch } : row)));
  }

  if (overlayQuery.isError) {
    return (
      <Alert severity="error" data-testid="semantic-overlay-load-error">
        {safeDisplayError(overlayQuery.error)}
      </Alert>
    );
  }

  return (
    <Stack spacing={2} data-testid="semantic-overlay-panel">
      <Typography variant="subtitle1" fontWeight={600} data-testid="semantic-overlay-heading">
        Semantic catalog (metrics)
      </Typography>
      <Typography variant="body2" color="text.secondary">
        Relabel, hide, or narrow grains for this tenant without a deploy. Formulas stay locked.
        New metrics may only be a ratio or alias of same-family handler-backed metrics.
      </Typography>
      {saveError ? (
        <Alert severity="error" data-testid="semantic-overlay-save-error">
          {saveError}
        </Alert>
      ) : null}
      {saveOk ? (
        <Alert severity="success" data-testid="semantic-overlay-save-ok">
          {saveOk}
        </Alert>
      ) : null}

      <Typography variant="subtitle2">Platform metrics</Typography>
      <Stack spacing={2}>
        {baseMetrics.map((m) => (
          <Box key={m.key} data-testid={`semantic-overlay-metric-${m.key}`}>
            <Stack direction={{ xs: 'column', md: 'row' }} spacing={1} alignItems={{ md: 'center' }}>
              <TextField
                label={`${m.key} label`}
                size="small"
                value={labels[m.key] || ''}
                onChange={(e) => setLabels((prev) => ({ ...prev, [m.key]: e.target.value }))}
                inputProps={{ 'data-testid': `semantic-overlay-label-${m.key}` }}
                sx={{ minWidth: 220, flex: 1 }}
              />
              <FormControlLabel
                control={
                  <Switch
                    checked={Boolean(hidden[m.key])}
                    onChange={(e) => setHidden((prev) => ({ ...prev, [m.key]: e.target.checked }))}
                    slotProps={{ input: { 'data-testid': `semantic-overlay-hide-${m.key}` } }}
                  />
                }
                label="Hide"
              />
              <FormControl size="small" sx={{ minWidth: 220 }}>
                <InputLabel id={`semantic-overlay-grains-${m.key}-label`}>Allowed grains</InputLabel>
                <Select
                  labelId={`semantic-overlay-grains-${m.key}-label`}
                  multiple
                  label="Allowed grains"
                  value={grainTokens[m.key] || []}
                  onChange={(e) => {
                    const value = e.target.value;
                    setGrainTokens((prev) => ({
                      ...prev,
                      [m.key]: typeof value === 'string' ? value.split(',') : value,
                    }));
                  }}
                  renderValue={(selected) => selected.map((t) => `{${t}}`).join('; ')}
                  inputProps={{ 'data-testid': `semantic-overlay-grains-${m.key}` }}
                >
                  {m.allowed_grains.map((set) => {
                    const token = grainToken(set);
                    return (
                      <MenuItem key={token} value={token}>
                        <Checkbox checked={(grainTokens[m.key] || []).includes(token)} />
                        {`{${token}}`}
                      </MenuItem>
                    );
                  })}
                </Select>
              </FormControl>
            </Stack>
            <Typography variant="caption" color="text.disabled" data-testid={`semantic-overlay-locked-${m.key}`}>
              Locked formula · {m.locked.owner_surface}
            </Typography>
          </Box>
        ))}
      </Stack>

      <Divider />
      <Stack direction="row" spacing={1} alignItems="center">
        <Typography variant="subtitle2">Composed metrics</Typography>
        <Button size="small" onClick={addComposed} data-testid="semantic-overlay-add-composed">
          Add ratio or alias
        </Button>
      </Stack>
      {composed.map((row, index) => {
        const first = byKey.get(row.inputs[0] || '');
        const family = first?.fact_family;
        const inputOptions =
          row.op === 'alias'
            ? handlerBacked
            : handlerBacked.filter((m) => !family || m.fact_family === family);
        const inputMetrics = row.inputs.map((k) => byKey.get(k)).filter(Boolean) as BaseMetric[];
        const grainChoices = intersectGrainSets(inputMetrics.map((m) => m.allowed_grains));
        return (
          <Stack
            key={`${row.key}-${index}`}
            spacing={1}
            data-testid={`semantic-overlay-composed-${index}`}
            sx={{ pl: 1, borderLeft: 2, borderColor: 'divider' }}
          >
            <Stack direction={{ xs: 'column', md: 'row' }} spacing={1}>
              <TextField
                size="small"
                label="Key"
                value={row.key}
                onChange={(e) => updateComposed(index, { key: e.target.value })}
                inputProps={{ 'data-testid': `semantic-overlay-composed-key-${index}` }}
              />
              <TextField
                size="small"
                label="Label"
                value={row.label}
                onChange={(e) => updateComposed(index, { label: e.target.value })}
                inputProps={{ 'data-testid': `semantic-overlay-composed-label-${index}` }}
              />
              <FormControl size="small" sx={{ minWidth: 140 }}>
                <InputLabel id={`semantic-overlay-op-${index}-label`}>Op</InputLabel>
                <Select
                  labelId={`semantic-overlay-op-${index}-label`}
                  label="Op"
                  value={row.op}
                  onChange={(e) => {
                    const op = e.target.value as 'ratio' | 'alias';
                    updateComposed(index, {
                      op,
                      inputs: op === 'alias' ? row.inputs.slice(0, 1) : row.inputs,
                    });
                  }}
                  inputProps={{ 'data-testid': `semantic-overlay-composed-op-${index}` }}
                >
                  <MenuItem value="ratio">ratio</MenuItem>
                  <MenuItem value="alias">alias</MenuItem>
                </Select>
              </FormControl>
            </Stack>
            <Stack direction={{ xs: 'column', md: 'row' }} spacing={1}>
              {(row.op === 'alias' ? [0] : [0, 1]).map((slot) => (
                <FormControl key={slot} size="small" sx={{ minWidth: 200 }}>
                  <InputLabel id={`semantic-overlay-input-${index}-${slot}-label`}>
                    {row.op === 'ratio' ? (slot === 0 ? 'Numerator' : 'Denominator') : 'Alias of'}
                  </InputLabel>
                  <Select
                    labelId={`semantic-overlay-input-${index}-${slot}-label`}
                    label={row.op === 'ratio' ? (slot === 0 ? 'Numerator' : 'Denominator') : 'Alias of'}
                    value={row.inputs[slot] || ''}
                    onChange={(e) => {
                      const next = [...row.inputs];
                      next[slot] = String(e.target.value);
                      if (slot === 0 && row.op === 'ratio') {
                        const fam = byKey.get(String(e.target.value))?.fact_family;
                        if (fam && byKey.get(next[1] || '')?.fact_family !== fam) next[1] = '';
                      }
                      updateComposed(index, { inputs: next });
                    }}
                    inputProps={{ 'data-testid': `semantic-overlay-composed-input-${index}-${slot}` }}
                  >
                    {(slot === 0 ? handlerBacked : inputOptions).map((m) => (
                      <MenuItem key={m.key} value={m.key}>
                        {m.label} ({m.fact_family})
                      </MenuItem>
                    ))}
                  </Select>
                </FormControl>
              ))}
              <FormControl size="small" sx={{ minWidth: 180 }}>
                <InputLabel id={`semantic-overlay-composed-grain-${index}-label`}>Grain</InputLabel>
                <Select
                  labelId={`semantic-overlay-composed-grain-${index}-label`}
                  label="Grain"
                  value={grainToken(row.grain)}
                  onChange={(e) => updateComposed(index, { grain: parseGrainToken(String(e.target.value)) })}
                  inputProps={{ 'data-testid': `semantic-overlay-composed-grain-${index}` }}
                >
                  {grainChoices.map((set) => {
                    const token = grainToken(set);
                    return (
                      <MenuItem key={token} value={token}>
                        {`{${token}}`}
                      </MenuItem>
                    );
                  })}
                </Select>
              </FormControl>
              <Button color="inherit" onClick={() => setComposed((rows) => rows.filter((_, i) => i !== index))}>
                Remove
              </Button>
            </Stack>
          </Stack>
        );
      })}

      <Box>
        <Button
          variant="contained"
          disabled={mutation.isPending || overlayQuery.isPending}
          onClick={() => {
            setSaveOk(null);
            setSaveError(null);
            mutation.mutate();
          }}
          data-testid="semantic-overlay-save"
        >
          {mutation.isPending ? 'Saving…' : 'Save metric overlay'}
        </Button>
      </Box>
    </Stack>
  );
}
