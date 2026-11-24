'use client';

import { Box, Button, Checkbox, TextField, Typography } from '@mui/material';
import { useTheme } from '@mui/material/styles';
import { useState } from 'react';

import { tokensFor } from '@/theme/cipTokens';

import type { PinConfirmItem, StoreMapStore } from '../types';
import {
  confidenceText,
  confirmItemFor,
  methodLabel,
  proposalKey,
  selectableHighConfidence,
} from './pinProposals';

type Coordinates = { latitude: number; longitude: number; place?: string };

type Props = {
  /** Unpinned stores with a proposal, already filtered and ordered. */
  stores: StoreMapStore[];
  saving: boolean;
  /** Row error by proposal key. */
  errors: Record<string, string>;
  onConfirm: (items: PinConfirmItem[]) => void | Promise<unknown>;
  onSkip: (store: StoreMapStore) => void;
  inAside?: boolean;
};

function parseCoordinates(latitude: string, longitude: string): { value?: Coordinates; error?: string } {
  const lat = Number(latitude);
  const lon = Number(longitude);
  if (!latitude.trim() || !Number.isFinite(lat)) return { error: 'Latitude must be a number.' };
  if (!longitude.trim() || !Number.isFinite(lon)) return { error: 'Longitude must be a number.' };
  if (lat < -90 || lat > 90) return { error: 'Latitude must be between -90 and 90.' };
  if (lon < -180 || lon > 180) return { error: 'Longitude must be between -180 and 180.' };
  return { value: { latitude: lat, longitude: lon } };
}

/** The review list: a steward confirms, edits or skips every proposed pin. Nothing is saved before that. */
export function ProposedPinsPanel({ stores, saving, errors, onConfirm, onSkip, inAside = false }: Props) {
  const theme = useTheme();
  const tokens = tokensFor(theme.palette.mode);
  const [selected, setSelected] = useState<Set<string>>(() => new Set());
  const [editing, setEditing] = useState<string | null>(null);
  const [latitude, setLatitude] = useState('');
  const [longitude, setLongitude] = useState('');
  const [editError, setEditError] = useState<string | null>(null);
  const [chosen, setChosen] = useState<Record<string, Coordinates>>({});

  const present = new Set(stores.map(proposalKey));
  const selectedStores = stores.filter((store) => selected.has(proposalKey(store)));

  function toggle(key: string) {
    setSelected((current) => {
      const next = new Set([...current].filter((item) => present.has(item)));
      if (!next.delete(key)) next.add(key);
      return next;
    });
  }

  function startEdit(store: StoreMapStore) {
    const key = proposalKey(store);
    const start = chosen[key] ?? {
      latitude: store.location_suggestion?.latitude ?? 0,
      longitude: store.location_suggestion?.longitude ?? 0,
    };
    setEditing(key);
    setLatitude(String(start.latitude));
    setLongitude(String(start.longitude));
    setEditError(null);
  }

  function saveEdit(store: StoreMapStore) {
    const parsed = parseCoordinates(latitude, longitude);
    if (!parsed.value) {
      setEditError(parsed.error ?? 'Enter both coordinates.');
      return;
    }
    setEditError(null);
    void onConfirm([confirmItemFor(store, parsed.value)]);
  }

  const card = { border: `1px solid ${tokens.border.subtle}`, borderRadius: 1, p: 1 } as const;

  return (
    <Box data-testid="proposed-pins" sx={{ ...(inAside ? { mt: 0, display: 'flex', flexDirection: 'column', minHeight: 0, flex: '1 1 0' } : { mt: 1.5 }), minWidth: 0 }}>
      <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, flexWrap: 'wrap', mb: 0.5 }}>
        <Typography variant="subtitle2">Proposed pins ({stores.length})</Typography>
        <Box sx={{ display: 'flex', gap: 0.5, flexWrap: 'wrap', ml: { sm: 'auto' } }}>
          <Button size="small" variant="outlined" data-testid="proposal-select-high" disabled={saving || stores.length === 0}
            onClick={() => setSelected(new Set(selectableHighConfidence(stores).map(proposalKey)))}>
            Select high confidence
          </Button>
          <Button size="small" variant="contained" data-testid="proposal-confirm-selected"
            disabled={saving || selectedStores.length === 0}
            onClick={() => void onConfirm(selectedStores.map((store) => {
              const pick = chosen[proposalKey(store)];
              return confirmItemFor(store, pick);
            }))}>
            Confirm selected ({selectedStores.length})
          </Button>
        </Box>
      </Box>
      <Typography variant="caption" sx={{ display: 'block', color: tokens.text.muted, mb: 1 }}>
        These places come from the store names and the bundled place list. Nothing is saved until you confirm.
      </Typography>
      {stores.length === 0 ? (
        <Typography variant="body2" sx={{ color: tokens.text.secondary }}>
          No proposed pins. Stores without a proposal are listed under No coordinates.
        </Typography>
      ) : (
        <Box data-testid="proposed-pins-scroll" sx={{ ...(inAside ? { flex: 1, minHeight: 120, maxHeight: { xs: 280, md: 'none' } } : { maxHeight: { xs: 360, md: 420 } }), overflowY: 'auto', display: 'grid', gap: 1 }}>
          {stores.map((store) => {
            const key = proposalKey(store);
            const suggestion = store.location_suggestion;
            const alternatives = suggestion?.alternatives ?? [];
            const pick = chosen[key];
            const error = errors[key];
            return (
              <Box key={key} data-testid="proposed-pin-row" sx={{ ...card, minWidth: 0 }}>
                <Box sx={{ display: 'flex', gap: 0.5, alignItems: 'flex-start', minWidth: 0 }}>
                  <Checkbox size="small" sx={{ p: 0.5 }} data-testid="proposal-select"
                    checked={selected.has(key)} disabled={saving}
                    inputProps={{ 'aria-label': `Select ${store.site_label}` }}
                    onChange={() => toggle(key)} />
                  <Box sx={{ minWidth: 0, flex: 1 }}>
                    <Typography variant="body2" data-testid="proposal-label" sx={{ overflowWrap: 'anywhere' }}>
                      {store.site_label}
                    </Typography>
                    <Typography variant="caption" sx={{ display: 'block', color: tokens.text.secondary, overflowWrap: 'anywhere' }}>
                      {store.customer_name} · proposed place <strong>{pick?.place ?? suggestion?.place}</strong>
                      {' '}· {confidenceText(suggestion)}
                      {methodLabel(suggestion?.method) ? ` · ${methodLabel(suggestion?.method)}` : ''}
                    </Typography>
                    {suggestion?.named_centre ? (
                      <Typography variant="caption" sx={{ display: 'block', color: tokens.semantic.warning }} data-testid="proposal-named-centre">
                        Named shopping centre: {suggestion.named_centre}. The proposed place is the town of that name, which may be far from the centre. Check it.
                      </Typography>
                    ) : null}
                    {suggestion?.ambiguous ? (
                      <Typography variant="caption" sx={{ display: 'block', color: tokens.semantic.warning }}>
                        More than one place has this name. Check it, or pick another:
                      </Typography>
                    ) : null}
                    {alternatives.length > 0 ? (
                      <Box sx={{ display: 'flex', gap: 0.5, flexWrap: 'wrap', mt: 0.5 }}>
                        {alternatives.map((alt) => {
                          const active = pick?.latitude === alt.latitude && pick?.longitude === alt.longitude;
                          return (
                            <Button key={`${alt.latitude}:${alt.longitude}`} size="small" data-testid="proposal-alternative"
                              variant={active ? 'contained' : 'outlined'} disabled={saving}
                              onClick={() => setChosen((current) => ({
                                ...current, [key]: { latitude: alt.latitude, longitude: alt.longitude, place: alt.place },
                              }))}>
                              {alt.place} ({alt.latitude.toFixed(2)}, {alt.longitude.toFixed(2)})
                            </Button>
                          );
                        })}
                      </Box>
                    ) : null}
                  </Box>
                </Box>
                {error ? (
                  <Typography variant="caption" color="error" data-testid="proposal-error" sx={{ display: 'block' }}>
                    {error}
                  </Typography>
                ) : null}
                {editing === key ? (
                  <Box sx={{ display: 'flex', gap: 0.5, flexWrap: 'wrap', mt: 0.5 }}>
                    <TextField size="small" label="Latitude" value={latitude} data-testid="proposal-lat"
                      onChange={(event) => setLatitude(event.target.value)} sx={{ flex: '1 1 120px', minWidth: 0 }} />
                    <TextField size="small" label="Longitude" value={longitude} data-testid="proposal-lon"
                      onChange={(event) => setLongitude(event.target.value)} sx={{ flex: '1 1 120px', minWidth: 0 }} />
                    {editError ? (
                      <Typography variant="caption" color="error" data-testid="proposal-edit-error" sx={{ flexBasis: '100%' }}>
                        {editError}
                      </Typography>
                    ) : null}
                  </Box>
                ) : null}
                <Box data-testid="proposal-actions" sx={{ display: 'flex', gap: 0.5, flexWrap: 'wrap', mt: 0.5 }}>
                  {editing === key ? (
                    <>
                      <Button size="small" variant="contained" data-testid="proposal-save" disabled={saving}
                        onClick={() => saveEdit(store)}>Save pin</Button>
                      <Button size="small" data-testid="proposal-cancel" disabled={saving}
                        onClick={() => { setEditing(null); setEditError(null); }}>Cancel</Button>
                    </>
                  ) : (
                    <>
                      <Button size="small" variant="contained" data-testid="proposal-confirm" disabled={saving}
                        onClick={() => void onConfirm([confirmItemFor(store, pick)])}>Confirm</Button>
                      <Button size="small" data-testid="proposal-edit" disabled={saving}
                        onClick={() => startEdit(store)}>Edit</Button>
                      <Button size="small" data-testid="proposal-skip" disabled={saving}
                        onClick={() => onSkip(store)}>Skip</Button>
                    </>
                  )}
                </Box>
              </Box>
            );
          })}
        </Box>
      )}
    </Box>
  );
}
