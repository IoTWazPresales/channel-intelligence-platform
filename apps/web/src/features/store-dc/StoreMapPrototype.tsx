'use client';

import {
  Alert,
  Box,
  Button,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableRow,
  TextField,
  Typography,
} from '@mui/material';
import { useTheme } from '@mui/material/styles';
import { useState } from 'react';

import { MapAside, MapLayout, MapPanel } from '@/features/maps/MapCanvas';
import { useMapSettings } from '@/features/settings/useMapSettings';
import { WorkbenchMap } from '@/features/workbench-ui/map/WorkbenchMap';
import type { Coordinates, WorkbenchPoint } from '@/features/workbench-ui/map/clustering';
import { safeDisplayError } from '@/lib/api';
import { tokensFor } from '@/theme/cipTokens';

import { proposalKey } from './pins/pinProposals';
import { sellThroughColor } from './storeMapLayout';
import type { PinConfirmItem, StoreMapStore } from './types';

type Props = {
  stores: StoreMapStore[];
  mapStores: StoreMapStore[];
  points: Array<Coordinates & { id: string }>;
  scopeKey: string;
  selectedKey: string | null;
  saving: boolean;
  errors: Record<string, string>;
  onSelect: (key: string) => void;
  onAdjust: (key: string, coordinates: Coordinates) => void;
  onConfirm: (items: PinConfirmItem[]) => void | Promise<unknown>;
  onSkip: (store: StoreMapStore) => void;
};

function fmt(value: number | null | undefined): string {
  return value == null || !Number.isFinite(value)
    ? '-'
    : value.toLocaleString(undefined, { maximumFractionDigits: 2 });
}

function StoreFacts({ store }: { store: StoreMapStore }) {
  return (
    <Box component="dl" sx={{
      m: 0, display: 'grid', gridTemplateColumns: 'auto 1fr', gap: '4px 12px',
      '& dt': { color: 'text.secondary' }, '& dd': { m: 0, overflowWrap: 'anywhere' },
    }}>
      <dt>Customer</dt><dd>{store.customer_name ?? '-'}</dd>
      <dt>Store</dt><dd>{store.site_label}</dd>
      <dt>Place</dt><dd>{store.place_name ?? store.location_suggestion?.place ?? '-'}</dd>
      <dt>Last week&apos;s units</dt><dd>{fmt(store.last_week_units)}</dd>
      <dt>Stock on hand</dt><dd>{fmt(store.stock_on_hand)}</dd>
      <dt>Sell-through</dt>
      <dd>{store.sell_through == null ? '-' : `${fmt(store.sell_through * 100)}%`}</dd>
      <dt>Weeks of cover</dt><dd>{fmt(store.weeks_of_cover)}</dd>
    </Box>
  );
}

/** Store presentation around the shared engine; writes stay in the parent's existing confirm flow. */
export function StoreMapPrototype(props: Props) {
  const settings = useMapSettings();
  const tokens = tokensFor(useTheme().palette.mode);
  const [search, setSearch] = useState('');
  const [placing, setPlacing] = useState<string | null>(null);
  const byKey = new Map(props.stores.map((store) => [proposalKey(store), store]));
  const mapped = new Map(props.mapStores.map((store) => [proposalKey(store), store]));
  const points: WorkbenchPoint[] = props.points.flatMap((point) => {
    const store = mapped.get(point.id);
    return store ? [{
      ...point, label: store.site_label, proposed: !store.pinned, score: store.sell_through,
    }] : [];
  });
  const pointByKey = new Map(points.map((point) => [point.id, point]));
  const selected = props.selectedKey ? byKey.get(props.selectedKey) : undefined;
  const selectedPoint = props.selectedKey ? pointByKey.get(props.selectedKey) : undefined;
  const needle = search.trim().toLowerCase();
  const listed = props.stores.filter((store) => !needle
    || [store.site_label, store.place_name ?? '', store.customer_name ?? '']
      .join(' ').toLowerCase().includes(needle));
  const canPlace = !settings.pending && !settings.error && !!settings.settings.tilejsonUrl && !props.saving;

  return (
    <Box
      data-testid="store-map-prototype"
      onKeyDown={(event) => {
        if (event.key === 'Escape') setPlacing(null);
      }}
    >
      {placing && byKey.has(placing) ? (
        <Alert severity="info" sx={{ mb: 1 }} action={
          <Button color="inherit" size="small" onClick={() => setPlacing(null)}>Cancel</Button>
        }>
          Place {byKey.get(placing)!.site_label}: click the map, or focus the map and press Enter
          to use its centre. Nothing is saved until confirmed.
        </Alert>
      ) : null}
      <MapLayout>
        <MapPanel>
          {settings.pending ? (
            <Typography variant="body2">Loading map settings…</Typography>
          ) : settings.error ? (
            <Alert severity="error">Map settings could not load: {safeDisplayError(settings.error)}</Alert>
          ) : (
            <WorkbenchMap
              settings={settings.settings}
              points={points}
              fitKey={`${props.scopeKey}:${props.stores.map(proposalKey).sort().join('|')}`}
              selectedKey={props.selectedKey}
              onSelect={props.onSelect}
              colorForScore={(score) => sellThroughColor(score, tokens.semantic.success, tokens.semantic.danger)}
              renderHover={(key) => {
                const store = byKey.get(key);
                return store ? <StoreFacts store={store} /> : null;
              }}
              onAdjust={props.saving ? undefined : props.onAdjust}
              placing={!!placing && !props.saving}
              onPlace={(coordinates) => {
                if (!placing || !byKey.has(placing) || props.saving) return;
                props.onAdjust(placing, coordinates);
                props.onSelect(placing);
                setPlacing(null);
              }}
              label="Store locations coloured by sell-through"
            />
          )}
        </MapPanel>
        <MapAside>
          <TextField
            size="small"
            label="Search stores"
            value={search}
            onChange={(event) => setSearch(event.target.value)}
          />
          <Box sx={{ maxHeight: 280, overflow: 'auto' }}>
            <Table size="small" aria-label="Stores linked to map">
              <TableHead>
                <TableRow><TableCell>Customer</TableCell><TableCell>Store</TableCell><TableCell>Pin</TableCell></TableRow>
              </TableHead>
              <TableBody>
                {listed.map((store) => {
                  const key = proposalKey(store);
                  const point = pointByKey.get(key);
                  return (
                    <TableRow
                      key={key}
                      selected={props.selectedKey === key}
                      data-testid="prototype-store-row"
                      data-store-key={key}
                      onClick={() => props.onSelect(key)}
                      sx={{ cursor: 'pointer' }}
                    >
                      <TableCell>{store.customer_name ?? '-'}</TableCell>
                      <TableCell>
                        <Button
                          size="small"
                          aria-pressed={props.selectedKey === key}
                          onClick={(event) => {
                            event.stopPropagation();
                            props.onSelect(key);
                          }}
                        >{store.site_label}</Button>
                      </TableCell>
                      <TableCell>{point ? (store.pinned ? 'Confirmed' : 'Proposed') : 'No coordinates'}</TableCell>
                    </TableRow>
                  );
                })}
              </TableBody>
            </Table>
            {!listed.length ? <Typography variant="body2">No stores match this view.</Typography> : null}
          </Box>
          {selected ? (
            <Box
              data-testid="prototype-store-detail"
              sx={{ p: 1.5, border: `1px solid ${tokens.border.subtle}`, borderRadius: 1 }}
            >
              <Typography variant="subtitle2" sx={{ mb: 1 }}>Store detail</Typography>
              <StoreFacts store={selected} />
              {!selected.pinned ? (
                <>
                  <Typography variant="caption" sx={{ display: 'block', mt: 1 }}>
                    {selectedPoint
                      ? `Proposed coordinates: ${selectedPoint.latitude.toFixed(5)}, ${selectedPoint.longitude.toFixed(5)}. Drag to adjust.`
                      : selected.location_suggestion?.reason === 'multiple'
                        ? 'More than one place matches. Drop a pin.'
                        : 'No place match. Drop a pin.'}
                    {' '}Nothing is saved until you confirm.
                  </Typography>
                  {selected.location_suggestion?.licence ? (
                    <Typography variant="caption" sx={{ display: 'block' }}>
                      {selected.location_suggestion.licence}
                    </Typography>
                  ) : null}
                  {props.errors[proposalKey(selected)] ? (
                    <Alert severity="error" sx={{ mt: 1 }}>{props.errors[proposalKey(selected)]}</Alert>
                  ) : null}
                  <Box sx={{ display: 'flex', gap: 0.5, flexWrap: 'wrap', mt: 1 }}>
                    {selectedPoint ? (
                      <Button
                        size="small"
                        variant="contained"
                        disabled={props.saving}
                        onClick={() => void props.onConfirm([{
                          customer_id: selected.customer_id,
                          site_label: selected.site_label,
                          latitude: selectedPoint.latitude,
                          longitude: selectedPoint.longitude,
                        }])}
                      >Confirm location</Button>
                    ) : null}
                    <Button
                      size="small"
                      disabled={!canPlace}
                      onClick={() => setPlacing(proposalKey(selected))}
                    >{selectedPoint ? 'Place elsewhere' : 'Drop pin'}</Button>
                    <Button size="small" disabled={props.saving} onClick={() => props.onSkip(selected)}>Skip</Button>
                  </Box>
                </>
              ) : null}
            </Box>
          ) : (
            <Typography variant="body2" color="text.secondary">Select a store on the map or in the list.</Typography>
          )}
        </MapAside>
      </MapLayout>
    </Box>
  );
}
