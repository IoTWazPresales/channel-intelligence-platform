'use client';

import { Box, Button, TextField, Typography } from '@mui/material';
import { useTheme } from '@mui/material/styles';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useRef, useState } from 'react';
import type { PointerEvent } from 'react';

import {
  DEFAULT_MAP_SIZE,
  MapAside,
  MapCanvas,
  MapLayout,
  MapPanel,
} from '@/features/maps/MapCanvas';
import { MapMarker } from '@/features/maps/MapMarker';
import { MapViewControls } from '@/features/maps/MapViewControls';
import { panLimits } from '@/features/maps/mapView';
import { useMapView } from '@/features/maps/useMapView';
import { apiGet, apiPost, safeDisplayError } from '@/lib/api';
import { tokensFor } from '@/theme/cipTokens';

import { PinLegend } from './pins/PinLegend';
import { proposedStores } from './pins/pinProposals';
import { ProposedPinsPanel } from './pins/ProposedPinsPanel';
import { useProposalConfirm } from './pins/useProposalConfirm';
import {
  finiteCoordinates,
  projectStores,
  sellThroughColor,
  spreadOverlaps,
  storeMapBounds,
  unprojectStore,
} from './storeMapLayout';
import type { StoreMapPayload, StoreMapStore } from './types';

function fmt(value: number | null | undefined): string {
  if (value == null || Number.isNaN(value)) return '—';
  return Number(value).toLocaleString(undefined, { maximumFractionDigits: 2 });
}

function storeKey(store: StoreMapStore): string {
  return `${store.customer_id}:${store.site_label}`;
}

function storePlace(store: StoreMapStore): string {
  const name = store.place_name?.trim();
  return name || store.site_label;
}

type Coordinates = { latitude: number; longitude: number };
type MapBounds = ReturnType<typeof storeMapBounds>;

// Overlap spacing and click target for pins: dense metros keep every pin reachable.
const PIN_SPREAD_PX = 16;
const PIN_HIT_PX = 22;
// Past this many pins the glow around each marker would blur into one blob.
const GLOW_PIN_LIMIT = 60;

export function StoreMap() {
  const theme = useTheme();
  const tokens = tokensFor(theme.palette.mode);
  const queryClient = useQueryClient();
  const proposalConfirm = useProposalConfirm();
  const [customerId, setCustomerId] = useState<number | 'all'>('all');
  const [hoverKey, setHoverKey] = useState<string | null>(null);
  const [selectedKey, setSelectedKey] = useState<string | null>(null);
  const [pinFor, setPinFor] = useState<string | null>(null);
  const [latitude, setLatitude] = useState('');
  const [longitude, setLongitude] = useState('');
  const [pinError, setPinError] = useState<string | null>(null);
  const [pinErrorKey, setPinErrorKey] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [unpinnedQuery, setUnpinnedQuery] = useState('');
  const [overrides, setOverrides] = useState<Record<string, Coordinates>>({});
  const [rejected, setRejected] = useState<Set<string>>(() => new Set());
  const [activePinKey, setActivePinKey] = useState<string | null>(null);
  const [dragBounds, setDragBounds] = useState<MapBounds | null>(null);
  const canvasRef = useRef<HTMLDivElement>(null);
  const [mapPx, setMapPx] = useState(DEFAULT_MAP_SIZE);
  const savingRef = useRef(false);
  const dragRef = useRef<{
    key: string;
    pointerId: number;
    clientX: number;
    clientY: number;
    x: number;
    y: number;
    width: number;
    height: number;
    bounds: MapBounds;
    moved: boolean;
  } | null>(null);

  const mapQuery = useQuery({
    queryKey: ['store-dc-map'],
    queryFn: ({ signal }) => apiGet<StoreMapPayload>('/api/v1/store-dc/map', { signal }),
    staleTime: 30_000,
  });

  const stores = mapQuery.data?.stores ?? [];
  const visible =
    customerId === 'all' ? stores : stores.filter((store) => store.customer_id === customerId);
  // A store with no usable coordinates is never drawn (not at a corner, not at 0,0): it stays in
  // the "No coordinates" list.
  const pinned = visible.filter(
    (store) => store.pinned && finiteCoordinates(store.latitude, store.longitude)
  );
  const suggestions = visible.filter(
    (store) =>
      !store.pinned &&
      !rejected.has(storeKey(store)) &&
      store.location_suggestion?.outcome === 'suggest' &&
      finiteCoordinates(store.location_suggestion.latitude, store.location_suggestion.longitude)
  );
  const suggestedKeys = new Set(suggestions.map(storeKey));
  const proposalList = proposedStores(visible, rejected);
  const mapStores = [...pinned, ...suggestions];
  const mappedKeys = new Set(mapStores.map(storeKey));
  const unpinned = visible.filter((store) => !mappedKeys.has(storeKey(store)));
  const points = mapStores.map((store) => ({
    id: storeKey(store),
    ...(store.pinned
      ? finiteCoordinates(store.latitude, store.longitude)!
      : (overrides[storeKey(store)] ??
        finiteCoordinates(
          store.location_suggestion!.latitude,
          store.location_suggestion!.longitude
        )!)),
  }));
  const pointOf = new Map(points.map((point) => [point.id, point]));
  const needle = unpinnedQuery.trim().toLowerCase();
  const listed = needle
    ? unpinned.filter((store) =>
        [storePlace(store), store.site_label, store.customer_name ?? '']
          .join(' ')
          .toLowerCase()
          .includes(needle)
      )
    : unpinned;
  // The default view fits the continent the pins are in; the steward can pan and zoom away from
  // it. A pin drag freezes whichever view it started in.
  const fit = storeMapBounds(points);
  const mapView = useMapView(fit, panLimits(fit, points), canvasRef);
  const bounds = dragBounds ?? mapView.bounds;
  const projected = projectStores(points, bounds);
  const placed = spreadOverlaps(projected, mapPx, PIN_SPREAD_PX);
  const placeOf = new Map(placed.map((pin) => [pin.id, pin]));
  const selected = visible.find((store) => storeKey(store) === selectedKey) ?? null;
  const hover = mapStores.find((store) => storeKey(store) === hoverKey) ?? null;
  const activePin = suggestions.find((store) => storeKey(store) === activePinKey) ?? null;
  const activePosition = activePin ? placeOf.get(storeKey(activePin)) : null;

  // A different customer is a different set of pins: fit the view to them again.
  function chooseCustomer(next: number | 'all') {
    setCustomerId(next);
    mapView.reset();
  }

  function startDrag(event: PointerEvent<HTMLButtonElement>, key: string) {
    if (savingRef.current || event.button !== 0) return;
    setActivePinKey(key);
    const rect = canvasRef.current?.getBoundingClientRect();
    const point = projected.find((item) => item.id === key);
    if (!rect?.width || !rect.height || !point) return;
    dragRef.current = {
      key,
      pointerId: event.pointerId,
      clientX: event.clientX,
      clientY: event.clientY,
      x: point.x,
      y: point.y,
      width: rect.width,
      height: rect.height,
      bounds,
      moved: false,
    };
    setDragBounds(bounds);
    event.currentTarget.setPointerCapture?.(event.pointerId);
    event.preventDefault();
  }

  function moveDrag(event: PointerEvent<HTMLButtonElement>) {
    const drag = dragRef.current;
    if (!drag || event.pointerId !== drag.pointerId) return;
    if (!drag.moved && event.clientX === drag.clientX && event.clientY === drag.clientY) return;
    drag.moved = true;
    // Use the projection at pointer down throughout this gesture. The visual
    // overlap offset stays out of the geographic coordinates.
    const coordinates = unprojectStore(
      drag.x + ((event.clientX - drag.clientX) / drag.width) * 100,
      drag.y + ((event.clientY - drag.clientY) / drag.height) * 100,
      drag.bounds
    );
    setOverrides((current) => ({
      ...current,
      [drag.key]: {
        latitude: Math.max(-90, Math.min(90, coordinates.latitude)),
        longitude: Math.max(-180, Math.min(180, coordinates.longitude)),
      },
    }));
  }

  function endDrag(event: PointerEvent<HTMLButtonElement>, cancelled = false) {
    if (dragRef.current?.pointerId !== event.pointerId) return;
    if (!cancelled) moveDrag(event);
    dragRef.current = null;
    setDragBounds(null);
    if (event.currentTarget.hasPointerCapture?.(event.pointerId)) {
      event.currentTarget.releasePointerCapture(event.pointerId);
    }
  }

  function rejectSuggestion(store: StoreMapStore) {
    const key = storeKey(store);
    setRejected((current) => new Set(current).add(key));
    proposalConfirm.clearError(key);
    setActivePinKey(null);
    setHoverKey(null);
    setPinError(null);
    setPinErrorKey(null);
  }

  async function postPin(store: StoreMapStore, lat: number, lon: number) {
    if (savingRef.current) return;
    savingRef.current = true;
    const key = storeKey(store);
    setSaving(true);
    setPinError(null);
    setPinErrorKey(key);
    try {
      const saved = await apiPost<StoreMapStore>('/api/v1/store-dc/pins', {
        customer_id: store.customer_id,
        site_label: store.site_label,
        latitude: lat,
        longitude: lon,
      });
      queryClient.setQueryData<StoreMapPayload>(
        ['store-dc-map'],
        (current) =>
          current && {
            ...current,
            stores: current.stores.map((item) => (storeKey(item) === key ? saved : item)),
          }
      );
      setActivePinKey(null);
      setPinFor(null);
      setLatitude('');
      setLongitude('');
      setPinErrorKey(null);
      await queryClient.invalidateQueries({ queryKey: ['store-dc-map'] });
    } catch (error) {
      setPinError(safeDisplayError(error));
      setPinErrorKey(key);
      if (suggestedKeys.has(key)) setActivePinKey(key);
    } finally {
      savingRef.current = false;
      setSaving(false);
    }
  }

  async function savePin(store: StoreMapStore) {
    const lat = Number(latitude);
    const lon = Number(longitude);
    if (!Number.isFinite(lat) || !Number.isFinite(lon)) {
      setPinError('Enter both coordinates.');
      setPinErrorKey(storeKey(store));
      return;
    }
    await postPin(store, lat, lon);
  }

  async function confirmSuggestion(store: StoreMapStore) {
    const suggestion = store.location_suggestion;
    if (
      suggestion?.outcome !== 'suggest' ||
      suggestion.latitude == null ||
      suggestion.longitude == null
    ) {
      return;
    }
    const coordinates = overrides[storeKey(store)] ?? suggestion;
    await postPin(store, coordinates.latitude!, coordinates.longitude!);
  }

  return (
    <Box data-testid="store-map" sx={{ mt: 1.5 }}>
      <Box
        sx={{ display: 'flex', justifyContent: 'space-between', gap: 1, flexWrap: 'wrap', mb: 1 }}
      >
        <Typography variant="subtitle1">Stores</Typography>
        <Box
          data-testid="store-map-legend"
          sx={{ display: 'flex', alignItems: 'center', gap: 1, minWidth: 180 }}
        >
          <Typography variant="caption" sx={{ color: tokens.text.secondary }}>
            Worst
          </Typography>
          <Box
            sx={{
              flex: 1,
              height: 8,
              borderRadius: 4,
              background: `linear-gradient(90deg, ${tokens.semantic.danger}, ${tokens.semantic.success})`,
            }}
          />
          <Typography variant="caption" sx={{ color: tokens.text.secondary }}>
            Best
          </Typography>
        </Box>
      </Box>
      <Typography variant="caption" sx={{ display: 'block', color: tokens.text.muted, mb: 1 }}>
        {mapQuery.data?.legend?.formula ??
          "last week's units / (last week's units + stock on hand)"}
      </Typography>
      <PinLegend />
      {mapQuery.isLoading ? (
        <Typography
          variant="body2"
          sx={{ color: tokens.text.secondary }}
          data-testid="store-map-loading"
        >
          Loading stores.
        </Typography>
      ) : null}
      {mapQuery.isError ? (
        <Typography variant="body2" color="error">
          Store map could not be loaded: {safeDisplayError(mapQuery.error)}
        </Typography>
      ) : null}
      <Box
        sx={{ display: 'flex', gap: 0.5, flexWrap: 'wrap', mb: 1 }}
        data-testid="store-map-customers"
      >
        <Button
          size="small"
          variant={customerId === 'all' ? 'contained' : 'outlined'}
          onClick={() => chooseCustomer('all')}
        >
          All customers
        </Button>
        {(mapQuery.data?.customers ?? []).map((customer) => (
          <Button
            key={customer.id}
            size="small"
            variant={customerId === customer.id ? 'contained' : 'outlined'}
            onClick={() => chooseCustomer(customer.id)}
          >
            {customer.name}
          </Button>
        ))}
      </Box>
      <MapLayout>
        <MapPanel>
          <MapCanvas
            ref={canvasRef}
            data-testid="store-map-canvas"
            label="Store locations coloured by sell-through"
            bounds={bounds}
            onSizeChange={setMapPx}
            panHandlers={mapView.panHandlers}
            grabbing={mapView.grabbing}
          >
            {mapStores.length === 0 ? (
              <Typography variant="body2" sx={{ p: 2, color: tokens.text.secondary }}>
                No store has coordinates yet.
              </Typography>
            ) : null}
            {mapStores.map((store) => {
              const key = storeKey(store);
              const unconfirmed = suggestedKeys.has(key);
              const coordinates = pointOf.get(key)!;
              const pin = placeOf.get(key);
              if (!pin) return null;
              const color = sellThroughColor(
                store.sell_through,
                tokens.semantic.success,
                tokens.semantic.danger
              );
              const on = unconfirmed ? activePinKey === key : selectedKey === key;
              // The Shipments marker: solid = a pin a steward saved, hollow dashed = a proposal
              // (see PinLegend). The sell-through colour stays the marker colour.
              return (
                <MapMarker
                  key={key}
                  x={pin.x}
                  y={pin.y}
                  offset={{ dx: pin.dx, dy: pin.dy }}
                  hit={PIN_HIT_PX}
                  color={color}
                  size={on ? 16 : 11}
                  selected={on}
                  hollow={unconfirmed}
                  glow={mapStores.length <= GLOW_PIN_LIMIT}
                  zIndex={on ? 1 : undefined}
                  cursor={unconfirmed ? 'grab' : 'pointer'}
                  touchAction={unconfirmed ? 'none' : 'auto'}
                  data-testid={unconfirmed ? 'store-dot-unconfirmed' : 'store-dot'}
                  data-pin-state={unconfirmed ? 'unconfirmed' : 'confirmed'}
                  data-latitude={coordinates.latitude}
                  data-longitude={coordinates.longitude}
                  data-customer-id={store.customer_id}
                  aria-label={`${storePlace(store)}, ${store.site_label}, ${store.customer_name ?? ''}`}
                  aria-pressed={unconfirmed ? undefined : on}
                  onMouseEnter={() => setHoverKey(key)}
                  onMouseLeave={() => setHoverKey((current) => (current === key ? null : current))}
                  onFocus={() => setHoverKey(key)}
                  onBlur={() => setHoverKey((current) => (current === key ? null : current))}
                  onClick={() => (unconfirmed ? setActivePinKey(key) : setSelectedKey(key))}
                  onPointerDown={unconfirmed ? (event) => startDrag(event, key) : undefined}
                  onPointerMove={unconfirmed ? moveDrag : undefined}
                  onPointerUp={unconfirmed ? (event) => endDrag(event) : undefined}
                  onPointerCancel={unconfirmed ? (event) => endDrag(event, true) : undefined}
                  onLostPointerCapture={unconfirmed ? (event) => endDrag(event, true) : undefined}
                />
              );
            })}
            <MapViewControls
              data-testid="store-map-view-controls"
              onZoomIn={mapView.zoomIn}
              onZoomOut={mapView.zoomOut}
              onReset={mapView.reset}
              canZoomIn={mapView.canZoomIn}
              canZoomOut={mapView.canZoomOut}
              canReset={mapView.panned}
            />
            {activePin && activePosition ? (
              <Box
                data-no-pan
                data-testid="store-pin-actions"
                sx={{
                  position: 'absolute',
                  left: `clamp(8px, ${activePosition.x}%, calc(100% - 240px))`,
                  top: `clamp(8px, ${activePosition.y}% + 16px, calc(100% - 130px))`,
                  width: 220,
                  maxWidth: '90%',
                  p: 1,
                  zIndex: 2,
                  borderRadius: 1,
                  bgcolor: tokens.bg.elevated,
                  border: `1px solid ${tokens.border.strong}`,
                }}
              >
                <Typography
                  variant="caption"
                  data-testid="place-suggestion"
                  sx={{ display: 'block' }}
                >
                  {activePin.site_label}: confirm location · {activePin.location_suggestion?.place}.{' '}
                  {activePin.location_suggestion?.licence}. Drag to adjust. Nothing is saved until
                  you confirm.
                </Typography>
                <Button
                  size="small"
                  data-testid="confirm-suggestion"
                  disabled={saving}
                  onClick={() => void confirmSuggestion(activePin)}
                >
                  Confirm location
                </Button>
                <Button
                  size="small"
                  data-testid="reject-suggestion"
                  disabled={saving}
                  onClick={() => rejectSuggestion(activePin)}
                >
                  Reject
                </Button>
                {pinError && pinErrorKey === storeKey(activePin) ? (
                  <Typography
                    variant="caption"
                    color="error"
                    data-testid="pin-error"
                    sx={{ display: 'block' }}
                  >
                    {pinError}
                  </Typography>
                ) : null}
              </Box>
            ) : null}
            {hover ? (
              <Box
                data-testid="store-map-hover"
                sx={{
                  position: 'absolute',
                  left: 8,
                  bottom: 8,
                  maxWidth: '90%',
                  px: 1,
                  py: 0.75,
                  borderRadius: 1,
                  bgcolor: tokens.bg.elevated,
                  border: `1px solid ${tokens.border.strong}`,
                  color: tokens.text.primary,
                  fontSize: 12,
                  pointerEvents: 'none',
                }}
              >
                <div>{storePlace(hover)}</div>
                <div>{hover.site_label}</div>
                <div>{hover.customer_name}</div>
                <div>Last week {fmt(hover.last_week_units)} units</div>
                <div>Stock on hand {fmt(hover.stock_on_hand)}</div>
                <div>Weeks of cover {fmt(hover.weeks_of_cover)}</div>
                {suggestedKeys.has(storeKey(hover)) ? (
                  <div>
                    confirm location · {hover.location_suggestion?.place} ·{' '}
                    {hover.location_suggestion?.licence}
                  </div>
                ) : null}
              </Box>
            ) : null}
          </MapCanvas>
        </MapPanel>
        <MapAside>
          <Box
            data-testid="store-map-unpinned"
            sx={{ height: mapPx.h, display: 'flex', flexDirection: 'column', minHeight: 0 }}
          >
            <Typography variant="caption" sx={{ color: tokens.text.secondary }}>
              No coordinates
            </Typography>
            <TextField
              size="small"
              placeholder="Search stores"
              value={unpinnedQuery}
              onChange={(event) => setUnpinnedQuery(event.target.value)}
              inputProps={{ 'aria-label': 'Search stores', 'data-testid': 'store-map-search' }}
              sx={{ mt: 0.5 }}
            />
            <Box
              data-testid="store-map-unpinned-scroll"
              sx={{ overflowY: 'auto', flex: 1, minHeight: 0, mt: 0.5 }}
            >
              {unpinned.length === 0 ? (
                <Typography variant="body2" sx={{ color: tokens.text.muted }}>
                  Every store in this view has a pin.
                </Typography>
              ) : listed.length === 0 ? (
                <Typography variant="body2" sx={{ color: tokens.text.muted }}>
                  No store matches that search.
                </Typography>
              ) : (
                listed.map((store) => {
                  const key = storeKey(store);
                  const place = storePlace(store);
                  return (
                    <Box key={key} sx={{ mt: 1 }}>
                      <Typography variant="body2">
                        {place}
                        {place !== store.site_label ? (
                          <Box component="span" sx={{ color: tokens.text.secondary }}>
                            {' '}
                            · {store.site_label}
                          </Box>
                        ) : null}
                        <Box component="span" sx={{ color: tokens.text.secondary }}>
                          {' '}
                          · {store.customer_name}
                        </Box>
                      </Typography>
                      {store.location_suggestion?.outcome === 'manual' ? (
                        <Typography
                          variant="caption"
                          sx={{ display: 'block', color: tokens.text.secondary }}
                          data-testid="place-manual"
                        >
                          {store.location_suggestion.reason === 'multiple'
                            ? 'More than one place matches. Drop a pin.'
                            : 'No place match. Drop a pin.'}
                        </Typography>
                      ) : null}
                      {pinError && pinErrorKey === key ? (
                        <Typography
                          variant="caption"
                          color="error"
                          data-testid="pin-error"
                          sx={{ display: 'block' }}
                        >
                          {pinError}
                        </Typography>
                      ) : null}
                      <Button
                        size="small"
                        data-testid="drop-pin"
                        onClick={() => {
                          setPinFor(key);
                          setPinError(null);
                          setPinErrorKey(null);
                        }}
                      >
                        Drop pin
                      </Button>
                      {pinFor === key ? (
                        <Box sx={{ display: 'grid', gap: 0.5, mt: 0.5 }}>
                          <TextField
                            size="small"
                            label="Latitude"
                            value={latitude}
                            onChange={(event) => setLatitude(event.target.value)}
                            inputProps={{ 'data-testid': 'pin-latitude' }}
                          />
                          <TextField
                            size="small"
                            label="Longitude"
                            value={longitude}
                            onChange={(event) => setLongitude(event.target.value)}
                            inputProps={{ 'data-testid': 'pin-longitude' }}
                          />
                          <Button
                            size="small"
                            variant="contained"
                            disabled={saving}
                            onClick={() => void savePin(store)}
                          >
                            Save pin
                          </Button>
                        </Box>
                      ) : null}
                    </Box>
                  );
                })
              )}
            </Box>
          </Box>
        </MapAside>
      </MapLayout>
      <ProposedPinsPanel
        stores={proposalList}
        saving={saving || proposalConfirm.saving}
        errors={proposalConfirm.errors}
        onConfirm={proposalConfirm.confirm}
        onSkip={rejectSuggestion}
      />
      {selected ? (
        <Box data-testid="store-map-lines" sx={{ mt: 1.5 }}>
          <Typography variant="subtitle2">
            {storePlace(selected)} · {selected.site_label} · {selected.customer_name}
          </Typography>
          {selected.lines.length === 0 ? (
            <Typography variant="body2" sx={{ color: tokens.text.secondary }}>
              No product lines for this store.
            </Typography>
          ) : (
            selected.lines.map((line) => (
              <Typography key={line.product_id} variant="body2" data-testid="store-line">
                {line.sku ?? line.product_name} · {fmt(line.units)} units · stock{' '}
                {fmt(line.stock_on_hand)} · cover {fmt(line.weeks_of_cover)}
              </Typography>
            ))
          )}
        </Box>
      ) : null}
    </Box>
  );
}
