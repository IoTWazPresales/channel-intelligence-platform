'use client';

import { Box, Button, TextField, Typography } from '@mui/material';
import { useTheme } from '@mui/material/styles';
import { keepPreviousData, useQuery, useQueryClient } from '@tanstack/react-query';
import { lazy, Suspense, useEffect, useRef, useState } from 'react';
import type { PointerEvent } from 'react';

import {
  DEFAULT_MAP_SIZE,
  MapAside,
  MapCanvas,
  MapLayout,
  MapPanel,
} from '@/features/maps/MapCanvas';
import { MapHoverCard, MapHoverSectionLabel, MapHoverTitleRow } from '@/features/maps/mapHover';
import { MapMarker } from '@/features/maps/MapMarker';
import { MapViewControls } from '@/features/maps/MapViewControls';
import { lonSpanOf, panLimits } from '@/features/maps/mapView';
import { useMapView } from '@/features/maps/useMapView';
import { useMapSettings } from '@/features/settings/useMapSettings';
import { apiGet, apiPost, safeDisplayError } from '@/lib/api';
import { tokensFor } from '@/theme/cipTokens';

import { StoreMapPanelHeader } from './pins/PinLegend';
import { proposedStores } from './pins/pinProposals';
import { ProposedPinsPanel } from './pins/ProposedPinsPanel';
import { useProposalConfirm } from './pins/useProposalConfirm';
import { MAX_HIT_PX, clusterPins, meanSellThrough, type PinGroup } from './storeMapClusters';
import {
  STORE_MIN_LON_SPAN,
  finiteCoordinates,
  projectStores,
  sellThroughColor,
  spreadOverlaps,
  storeMapBounds,
  unprojectStore,
} from './storeMapLayout';
import type { PinConfirmItem, StoreMapPayload, StoreMapStore } from './types';

const StoreMapPrototype = lazy(() => import('./StoreMapPrototype').then((module) => ({
  default: module.StoreMapPrototype,
})));

function fmt(value: number | null | undefined): string {
  if (value == null || Number.isNaN(value)) return '-';
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

const PIN_SPREAD_PX = 16;
const SPREAD_HIT_PX = 16;
const OPEN_HIT_PX = 22;
const PIN_SIZE = 11;
const PIN_SIZE_SELECTED = 16;
const CLUSTER_FIT_PADDING = 1.8;
const CLUSTER_CARD_STORES = 5;

function hitFor(size: number, nearestPx: number): number {
  return Math.max(size + 2, Math.min(MAX_HIT_PX, Math.floor(nearestPx)));
}

function clusterSize(count: number): number {
  return PIN_SIZE_SELECTED + (String(count).length - 1) * 4;
}

export function StoreMap() {
  const theme = useTheme();
  const tokens = tokensFor(theme.palette.mode);
  const queryClient = useQueryClient();
  const proposalConfirm = useProposalConfirm();
  const mapSettings = useMapSettings();
  const useLibre = !mapSettings.pending && !!mapSettings.settings.tilejsonUrl;
  const [boardScope, setBoardScope] = useState<'reporting' | 'all'>('reporting');
  const [customerId, setCustomerId] = useState<number | 'all'>('all');
  const [hoverKey, setHoverKey] = useState<string | null>(null);
  const [hoverClusterId, setHoverClusterId] = useState<string | null>(null);
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
  const [movingKey, setMovingKey] = useState<string | null>(null);
  const [undoStack, setUndoStack] = useState<Array<{
    key: string;
    previous: Coordinates;
    next: Coordinates;
    persisted: boolean;
  }>>([]);
  const [dragBounds, setDragBounds] = useState<MapBounds | null>(null);
  const canvasRef = useRef<HTMLDivElement>(null);
  const [mapPx, setMapPx] = useState(DEFAULT_MAP_SIZE);
  const savingRef = useRef(false);
  const undoStackRef = useRef(undoStack);
  undoStackRef.current = undoStack;
  const adjustStartRef = useRef<Record<string, Coordinates>>({});
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
    previous: Coordinates;
    persisted: boolean;
    moved: boolean;
  } | null>(null);

  const mapQuery = useQuery({
    queryKey: ['store-dc-map', boardScope],
    queryFn: ({ signal }) => {
      const suffix = boardScope === 'reporting' ? '?reporting_only=true' : '';
      return apiGet<StoreMapPayload>(`/api/v1/store-dc/map${suffix}`, { signal });
    },
    staleTime: 30_000,
    placeholderData: keepPreviousData,
  });

  const stores = mapQuery.data?.stores ?? [];
  const visible =
    customerId === 'all' ? stores : stores.filter((store) => store.customer_id === customerId);
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
  // Manual drops exist only in local state and only participate in the prototype canvas.
  const suggestionKeys = new Set(suggestions.map(storeKey));
  const drafted = useLibre ? visible.filter((store) =>
    !store.pinned && !rejected.has(storeKey(store))
    && !suggestionKeys.has(storeKey(store)) && !!overrides[storeKey(store)]
  ) : [];
  const suggestedKeys = new Set([...suggestions, ...drafted].map(storeKey));
  const proposalList = proposedStores(visible, rejected);
  const mapStores = [...pinned, ...suggestions, ...drafted];
  const mappedKeys = new Set(mapStores.map(storeKey));
  const unpinned = visible.filter((store) => !mappedKeys.has(storeKey(store)));
  const points = mapStores.map((store) => ({
    id: storeKey(store),
    ...(overrides[storeKey(store)] ??
      (store.pinned
        ? finiteCoordinates(store.latitude, store.longitude)!
        : finiteCoordinates(store.location_suggestion!.latitude, store.location_suggestion!.longitude)!)),
  }));
  const pointOf = new Map(points.map((point) => [point.id, point]));
  const needle = unpinnedQuery.trim().toLowerCase();
  const listed = needle
    ? unpinned.filter((store) =>
        [storePlace(store), store.site_label, store.customer_name ?? '']
          .join(' ').toLowerCase().includes(needle)
      )
    : unpinned;

  const fit = storeMapBounds(points);
  const mapView = useMapView(fit, panLimits(fit, points), canvasRef, STORE_MIN_LON_SPAN);
  const bounds = dragBounds ?? mapView.bounds;
  const projected = projectStores(points, bounds);
  const atMaxZoom = lonSpanOf(bounds) <= STORE_MIN_LON_SPAN * 1.05;
  const stayOpen = new Set([activePinKey, selectedKey]);
  const groups = atMaxZoom
    ? []
    : clusterPins(
        projected.filter((pin) => !stayOpen.has(pin.id))
          .map((pin) => ({ ...pin, ...pointOf.get(pin.id)! })),
        mapPx
      );
  const singles = atMaxZoom
    ? spreadOverlaps(projected, mapPx, PIN_SPREAD_PX).map((pin) => ({ ...pin, hit: SPREAD_HIT_PX }))
    : [
        ...projected.filter((pin) => stayOpen.has(pin.id))
          .map((pin) => ({ ...pin, dx: 0, dy: 0, hit: OPEN_HIT_PX })),
        ...groups.filter((group) => group.members.length === 1).map((group) => ({
          id: group.id, x: group.x, y: group.y, dx: 0, dy: 0,
          hit: hitFor(PIN_SIZE, group.nearestPx),
        })),
      ];
  const clusters = groups.filter((group) => group.members.length > 1);
  const placeOf = new Map(singles.map((pin) => [pin.id, pin]));
  const storeByKey = new Map(mapStores.map((store) => [storeKey(store), store]));
  const hoverCluster = clusters.find((group) => group.id === hoverClusterId) ?? null;
  const selected = visible.find((store) => storeKey(store) === selectedKey) ?? null;
  const hover = mapStores.find((store) => storeKey(store) === hoverKey) ?? null;
  const hoverPin = hoverKey ? placeOf.get(hoverKey) : null;
  const activePin = suggestions.find((store) => storeKey(store) === activePinKey) ?? null;
  const activePosition = activePin ? placeOf.get(storeKey(activePin)) : null;

  function chooseCustomer(next: number | 'all') {
    setCustomerId(next);
    mapView.reset();
  }

  function showAllBoardCustomers() {
    setBoardScope('all');
    setCustomerId('all');
    mapView.reset();
  }

  function zoomToCluster(group: PinGroup) {
    setHoverClusterId(null);
    const next = storeMapBounds(group.members, STORE_MIN_LON_SPAN, CLUSTER_FIT_PADDING);
    if (lonSpanOf(next) < lonSpanOf(bounds)) mapView.fitTo(next);
    else mapView.zoomIn();
  }

  function startDrag(event: PointerEvent<HTMLButtonElement>, key: string, persisted: boolean) {
    if (savingRef.current || event.button !== 0) return;
    if (persisted && movingKey !== key) return;
    if (!persisted) setActivePinKey(key);
    const rect = canvasRef.current?.getBoundingClientRect();
    const point = projected.find((item) => item.id === key);
    const start = pointOf.get(key);
    if (!rect?.width || !rect.height || !point || !start) return;
    dragRef.current = {
      key, pointerId: event.pointerId, clientX: event.clientX, clientY: event.clientY,
      x: point.x, y: point.y, width: rect.width, height: rect.height, bounds,
      previous: { latitude: start.latitude, longitude: start.longitude },
      persisted, moved: false,
    };
    setDragBounds(bounds);
    event.currentTarget.setPointerCapture?.(event.pointerId);
    event.preventDefault();
  }

  function coordinatesFromDrag(
    event: PointerEvent<HTMLButtonElement>,
    drag: NonNullable<typeof dragRef.current>,
  ): Coordinates {
    const coordinates = unprojectStore(
      drag.x + ((event.clientX - drag.clientX) / drag.width) * 100,
      drag.y + ((event.clientY - drag.clientY) / drag.height) * 100,
      drag.bounds
    );
    return {
      latitude: Math.max(-90, Math.min(90, coordinates.latitude)),
      longitude: Math.max(-180, Math.min(180, coordinates.longitude)),
    };
  }

  function moveDrag(event: PointerEvent<HTMLButtonElement>) {
    const drag = dragRef.current;
    if (!drag || event.pointerId !== drag.pointerId) return;
    if (!drag.moved && event.clientX === drag.clientX && event.clientY === drag.clientY) return;
    drag.moved = true;
    setOverrides((current) => ({ ...current, [drag.key]: coordinatesFromDrag(event, drag) }));
  }

  async function endDrag(event: PointerEvent<HTMLButtonElement>, cancelled = false) {
    const drag = dragRef.current;
    if (!drag || drag.pointerId !== event.pointerId) return;
    const next = cancelled || !drag.moved ? null : coordinatesFromDrag(event, drag);
    if (next) setOverrides((current) => ({ ...current, [drag.key]: next }));
    dragRef.current = null;
    setDragBounds(null);
    if (event.currentTarget.hasPointerCapture?.(event.pointerId)) {
      event.currentTarget.releasePointerCapture(event.pointerId);
    }
    if (!next) return;
    if (drag.persisted) {
      const store = storeByKey.get(drag.key);
      if (!store) return;
      const saved = await postPin(store, next.latitude, next.longitude);
      if (!saved) {
        setOverrides((current) => ({ ...current, [drag.key]: drag.previous }));
        return;
      }
    }
    setUndoStack((current) => [...current, {
      key: drag.key, previous: drag.previous, next, persisted: drag.persisted,
    }]);
  }

  function rejectSuggestion(store: StoreMapStore) {
    const key = storeKey(store);
    setRejected((current) => new Set(current).add(key));
    setOverrides((current) => Object.fromEntries(Object.entries(current).filter(([id]) => id !== key)));
    proposalConfirm.clearError(key);
    setActivePinKey(null);
    setHoverKey(null);
    setPinError(null);
    setPinErrorKey(null);
  }

  function stagePrototypePin(key: string, coordinates: Coordinates) {
    if (proposalConfirm.saving || saving) return;
    if (!(key in adjustStartRef.current)) {
      const current = pointOf.get(key);
      if (current) adjustStartRef.current[key] = { latitude: current.latitude, longitude: current.longitude };
    }
    setOverrides((current) => ({ ...current, [key]: coordinates }));
    setRejected((current) => new Set([...current].filter((id) => id !== key)));
    proposalConfirm.clearError(key);
  }

  async function commitPrototypeAdjust(key: string, coordinates: Coordinates) {
    const previous = adjustStartRef.current[key];
    delete adjustStartRef.current[key];
    if (!previous) return;
    if (previous.latitude === coordinates.latitude && previous.longitude === coordinates.longitude) return;
    const store = storeByKey.get(key) ?? visible.find((entry) => storeKey(entry) === key);
    if (!store) return;
    const persisted = !!store.pinned;
    if (persisted) {
      const saved = await postPin(store, coordinates.latitude, coordinates.longitude);
      if (!saved) {
        setOverrides((current) => ({ ...current, [key]: previous }));
        return;
      }
    }
    setUndoStack((current) => [...current, { key, previous, next: coordinates, persisted }]);
  }

  function confirmPrototype(items: PinConfirmItem[]) {
    // Explicit panel edits/alternatives win. Otherwise include any locally staged map edit.
    return proposalConfirm.confirm(items.map((item) => {
      const coordinates = overrides[`${item.customer_id}:${item.site_label}`];
      return item.latitude == null && item.longitude == null && coordinates
        ? { ...item, ...coordinates }
        : item;
    }));
  }

  async function postPin(store: StoreMapStore, lat: number, lon: number): Promise<boolean> {
    if (savingRef.current) return false;
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
        (current) => current && {
          ...current,
          stores: current.stores.map((item) => (storeKey(item) === key ? saved : item)),
        }
      );
      setOverrides((current) => {
        const next = { ...current };
        delete next[key];
        return next;
      });
      setActivePinKey(null);
      setPinFor(null);
      setLatitude('');
      setLongitude('');
      setPinErrorKey(null);
      await queryClient.invalidateQueries({ queryKey: ['store-dc-map'] });
      return true;
    } catch (error) {
      setPinError(safeDisplayError(error));
      setPinErrorKey(key);
      if (suggestedKeys.has(key)) setActivePinKey(key);
      return false;
    } finally {
      savingRef.current = false;
      setSaving(false);
    }
  }

  async function undoMove() {
    const item = undoStackRef.current.at(-1);
    if (!item || savingRef.current) return;
    setUndoStack((current) => current.slice(0, -1));
    if (item.persisted) {
      const store = storeByKey.get(item.key) ?? visible.find((entry) => storeKey(entry) === item.key);
      if (!store) return;
      const saved = await postPin(store, item.previous.latitude, item.previous.longitude);
      if (!saved) setUndoStack((current) => [...current, item]);
      return;
    }
    setOverrides((current) => ({ ...current, [item.key]: item.previous }));
  }

  useEffect(() => {
    function onKey(event: KeyboardEvent) {
      if (!(event.ctrlKey || event.metaKey) || event.altKey || event.shiftKey) return;
      if (event.key.toLowerCase() !== 'z') return;
      const target = event.target as HTMLElement | null;
      if (typeof target?.closest === 'function' && target.closest('input, textarea, select, [contenteditable="true"]')) return;
      if (undoStackRef.current.length === 0 || savingRef.current) return;
      event.preventDefault();
      void undoMove();
    }
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  });

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
    if (suggestion?.outcome !== 'suggest' || suggestion.latitude == null || suggestion.longitude == null) return;
    const coordinates = overrides[storeKey(store)] ?? suggestion;
    await postPin(store, coordinates.latitude!, coordinates.longitude!);
  }

  const formula = mapQuery.data?.legend?.formula ?? "last week's units / (last week's units + stock on hand)";

  return (
    <Box data-testid="store-map" sx={{ mt: 1.5 }}>
      <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 1, flexWrap: 'wrap', mb: 1 }}>
        <Typography variant="subtitle1" sx={{ fontWeight: 700 }}>Stores</Typography>
        <Button
          size="small"
          data-testid="store-map-undo"
          disabled={undoStack.length === 0 || saving}
          onClick={() => void undoMove()}
        >
          Undo
        </Button>
      </Box>
      {mapQuery.isLoading ? (
        <Typography variant="body2" sx={{ color: tokens.text.secondary }} data-testid="store-map-loading">
          Loading stores.
        </Typography>
      ) : null}
      {mapQuery.isError ? (
        <Typography variant="body2" color="error">
          Store map could not be loaded: {safeDisplayError(mapQuery.error)}
        </Typography>
      ) : null}
      <Box sx={{ display: 'flex', gap: 0.5, flexWrap: 'wrap', mb: 1 }} data-testid="store-map-customers">
        <Button
          size="small"
          variant={boardScope === 'all' && customerId === 'all' ? 'contained' : 'outlined'}
          onClick={() => showAllBoardCustomers()}
        >
          All customers
        </Button>
        {(mapQuery.data?.customers ?? []).map((customer) => (
          <Button
            key={customer.id}
            size="small"
            variant={customerId === customer.id ? 'contained' : 'outlined'}
            onClick={() => chooseCustomer(customer.id)}
          >{customer.name}</Button>
        ))}
      </Box>
      {useLibre ? (
        <Suspense fallback={<Typography variant="body2">Loading map…</Typography>}>
          <StoreMapPrototype
            key={String(customerId)}
            stores={visible}
            mapStores={mapStores}
            points={points}
            scopeKey={String(customerId)}
            selectedKey={selectedKey}
            saving={saving || proposalConfirm.saving}
            errors={proposalConfirm.errors}
            proposalList={proposalList}
            formula={formula}
            asideHeight={mapPx.h}
            onSelect={setSelectedKey}
            onAdjust={stagePrototypePin}
            onAdjustEnd={commitPrototypeAdjust}
            onConfirm={confirmPrototype}
            onSkip={rejectSuggestion}
            canDrag={(key) => suggestedKeys.has(key) || movingKey === key}
            movingKey={movingKey}
            onToggleMove={(key) => setMovingKey((current) => current === key ? null : key)}
          />
        </Suspense>
      ) : (
        <MapLayout>
          <MapPanel>
            <StoreMapPanelHeader />
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
                <Typography variant="body2" sx={{ p: 2, color: tokens.text.secondary }}>No store has coordinates yet.</Typography>
              ) : null}
              {mapStores.map((store) => {
                const key = storeKey(store);
                const unconfirmed = suggestedKeys.has(key);
                const coordinates = pointOf.get(key)!;
                const pin = placeOf.get(key);
                if (!pin) return null;
                const color = sellThroughColor(store.sell_through, tokens.semantic.success, tokens.semantic.danger);
                const on = unconfirmed ? activePinKey === key : selectedKey === key;
                const canDrag = unconfirmed || movingKey === key;
                return (
                  <MapMarker
                    key={key}
                    x={pin.x}
                    y={pin.y}
                    offset={{ dx: pin.dx, dy: pin.dy }}
                    hit={pin.hit}
                    color={color}
                    size={on ? PIN_SIZE_SELECTED : PIN_SIZE}
                    selected={on}
                    proposed={unconfirmed}
                    glow
                    zIndex={on ? 1 : undefined}
                    cursor={canDrag ? 'grab' : 'pointer'}
                    touchAction={canDrag ? 'none' : 'auto'}
                    data-testid={unconfirmed ? 'store-dot-unconfirmed' : 'store-dot'}
                    data-pin-state={unconfirmed ? 'unconfirmed' : (movingKey === key ? 'moving' : 'confirmed')}
                    data-latitude={coordinates.latitude}
                    data-longitude={coordinates.longitude}
                    data-customer-id={store.customer_id}
                    aria-label={`${storePlace(store)}, ${store.site_label}, ${store.customer_name ?? ''}`}
                    aria-pressed={unconfirmed ? undefined : on}
                    onMouseEnter={() => setHoverKey(key)}
                    onMouseLeave={() => setHoverKey((current) => current === key ? null : current)}
                    onFocus={() => setHoverKey(key)}
                    onBlur={() => setHoverKey((current) => current === key ? null : current)}
                    onClick={() => unconfirmed ? setActivePinKey(key) : setSelectedKey(key)}
                    onPointerDown={canDrag ? (event) => void startDrag(event, key, !unconfirmed) : undefined}
                    onPointerMove={canDrag ? moveDrag : undefined}
                    onPointerUp={canDrag ? (event) => void endDrag(event) : undefined}
                    onPointerCancel={canDrag ? (event) => void endDrag(event, true) : undefined}
                    onLostPointerCapture={canDrag ? (event) => void endDrag(event, true) : undefined}
                  />
                );
              })}
              {clusters.map((group) => {
                const members = group.members.map((member) => storeByKey.get(member.id)!);
                const count = members.length;
                const proposed = members.some((store) => suggestedKeys.has(storeKey(store)));
                const color = sellThroughColor(
                  meanSellThrough(members.map((store) => store.sell_through)),
                  tokens.semantic.success, tokens.semantic.danger
                );
                const size = clusterSize(count);
                return (
                  <MapMarker
                    key={group.id}
                    x={group.x}
                    y={group.y}
                    hit={hitFor(size, group.nearestPx)}
                    color={color}
                    size={size}
                    proposed={proposed}
                    glow
                    data-testid="store-cluster"
                    data-cluster-count={count}
                    data-pin-state={proposed ? 'proposed' : 'confirmed'}
                    data-latitude={group.latitude}
                    data-longitude={group.longitude}
                    aria-label={`${count} stores near ${storePlace(members[0])}. Click to zoom in.`}
                    onMouseEnter={() => setHoverClusterId(group.id)}
                    onMouseLeave={() => setHoverClusterId((current) => current === group.id ? null : current)}
                    onFocus={() => setHoverClusterId(group.id)}
                    onBlur={() => setHoverClusterId((current) => current === group.id ? null : current)}
                    onClick={() => zoomToCluster(group)}
                  >
                    {count}
                  </MapMarker>
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
                    width: 220, maxWidth: '90%', p: 1, zIndex: 2, borderRadius: 1,
                    bgcolor: tokens.bg.elevated, border: `1px solid ${tokens.border.strong}`,
                  }}
                >
                  <Typography variant="caption" data-testid="place-suggestion" sx={{ display: 'block' }}>
                    {activePin.site_label}: confirm location · {activePin.location_suggestion?.place}.{' '}
                    {activePin.location_suggestion?.licence}. Drag to adjust. Nothing is saved until you confirm.
                  </Typography>
                  <Button size="small" data-testid="confirm-suggestion" disabled={saving} onClick={() => void confirmSuggestion(activePin)}>
                    Confirm location
                  </Button>
                  <Button size="small" data-testid="reject-suggestion" disabled={saving} onClick={() => rejectSuggestion(activePin)}>Reject</Button>
                  {pinError && pinErrorKey === storeKey(activePin) ? (
                    <Typography variant="caption" color="error" data-testid="pin-error" sx={{ display: 'block' }}>{pinError}</Typography>
                  ) : null}
                </Box>
              ) : null}
              {hoverCluster ? (
                <MapHoverCard
                  x={hoverCluster.x}
                  y={hoverCluster.y}
                  t={tokens}
                  testId="store-map-cluster-hover"
                  borderColor={tokens.semantic.warning}
                >
                  <Box sx={{ fontSize: 12, lineHeight: 1.45 }}>
                    {hoverCluster.members.length} stores here · click to zoom in
                  </Box>
                  <MapHoverSectionLabel t={tokens}>Stores</MapHoverSectionLabel>
                  {hoverCluster.members.slice(0, CLUSTER_CARD_STORES).map((member) => {
                    const store = storeByKey.get(member.id)!;
                    return (
                      <Box key={member.id} sx={{ fontSize: 12, lineHeight: 1.45 }}>
                        {storePlace(store)} · {store.customer_name}
                        {suggestedKeys.has(member.id) ? ' (proposed)' : ''}
                      </Box>
                    );
                  })}
                  {hoverCluster.members.length > CLUSTER_CARD_STORES ? (
                    <Box sx={{ fontSize: 11, color: tokens.text.secondary, mt: 0.75 }}>
                      +{hoverCluster.members.length - CLUSTER_CARD_STORES} more
                    </Box>
                  ) : null}
                </MapHoverCard>
              ) : null}
              {hover && hoverPin ? (
                <MapHoverCard x={hoverPin.x} y={hoverPin.y} t={tokens} testId="store-map-hover">
                  <MapHoverTitleRow>
                    <Box component="span" sx={{ fontSize: 13, fontWeight: 700 }}>{storePlace(hover)}</Box>
                    <Box component="span" sx={{ fontSize: 11, color: tokens.text.secondary }}>
                      {hover.site_label}
                    </Box>
                  </MapHoverTitleRow>
                  <Box sx={{ fontSize: 12, color: tokens.text.secondary, mt: 0.5 }}>{hover.customer_name}</Box>
                  <MapHoverSectionLabel t={tokens}>Sell-through</MapHoverSectionLabel>
                  <Box sx={{ fontSize: 12, lineHeight: 1.45, fontVariantNumeric: 'tabular-nums' }}>
                    Last week {fmt(hover.last_week_units)} units
                  </Box>
                  <Box sx={{ fontSize: 12, lineHeight: 1.45, fontVariantNumeric: 'tabular-nums' }}>
                    Stock on hand {fmt(hover.stock_on_hand)}
                  </Box>
                  <Box sx={{ fontSize: 12, lineHeight: 1.45, fontVariantNumeric: 'tabular-nums' }}>
                    Weeks of cover {fmt(hover.weeks_of_cover)}
                  </Box>
                  {suggestedKeys.has(storeKey(hover)) ? (
                    <Box sx={{ fontSize: 11, color: tokens.text.secondary, mt: 0.75 }}>
                      confirm location · {hover.location_suggestion?.place} · {hover.location_suggestion?.licence}
                    </Box>
                  ) : null}
                </MapHoverCard>
              ) : null}
            </MapCanvas>
            <Typography variant="caption" sx={{ display: 'block', px: 0.5, color: tokens.text.muted, fontSize: 11 }}>
              {formula}
            </Typography>
          </MapPanel>
          <MapAside>
            <Box data-testid="store-map-aside" sx={{ height: mapPx.h, display: 'flex', flexDirection: 'column', gap: 1.25, minHeight: 0 }}>
              {selected ? (
                <Box
                  data-testid="store-map-lines"
                  sx={{
                    bgcolor: tokens.bg.surface,
                    border: `1px solid ${tokens.border.subtle}`,
                    borderRadius: 1.5,
                    p: 1.25,
                    flexShrink: 0,
                    maxHeight: 150,
                    overflowY: 'auto',
                  }}
                >
                  <Typography variant="subtitle2">
                    {storePlace(selected)} · {selected.site_label} · {selected.customer_name}
                  </Typography>
                  {selected.pinned && finiteCoordinates(selected.latitude, selected.longitude) ? (
                    <Button
                      size="small"
                      data-testid="store-map-move-pin"
                      disabled={saving}
                      onClick={() => setMovingKey((current) => current === storeKey(selected) ? null : storeKey(selected))}
                    >
                      {movingKey === storeKey(selected) ? 'Done moving' : 'Move pin'}
                    </Button>
                  ) : null}
                  {selected.lines.length === 0 ? (
                    <Typography variant="body2" sx={{ color: tokens.text.secondary }}>No product lines for this store.</Typography>
                  ) : selected.lines.map((line) => (
                    <Typography key={line.product_id} variant="body2" data-testid="store-line">
                      {line.sku ?? line.product_name} · {fmt(line.units)} units · stock{' '}
                      {fmt(line.stock_on_hand)} · cover {fmt(line.weeks_of_cover)}
                    </Typography>
                  ))}
                </Box>
              ) : null}
              <Box
                sx={{
                  bgcolor: tokens.bg.surface,
                  border: `1px solid ${tokens.border.subtle}`,
                  borderRadius: 1.5,
                  p: 1.25,
                  display: 'flex',
                  flexDirection: 'column',
                  minHeight: 0,
                  flex: '1 1 0',
                }}
              >
                <ProposedPinsPanel
                  inAside
                  stores={proposalList}
                  saving={saving || proposalConfirm.saving}
                  errors={proposalConfirm.errors}
                  onConfirm={proposalConfirm.confirm}
                  onSkip={rejectSuggestion}
                />
              </Box>
              <Box
                data-testid="store-map-unpinned"
                sx={{
                  bgcolor: tokens.bg.surface,
                  border: `1px solid ${tokens.border.subtle}`,
                  borderRadius: 1.5,
                  p: 1.25,
                  display: 'flex',
                  flexDirection: 'column',
                  minHeight: 0,
                  flex: '1 1 0',
                }}
              >
              <Typography variant="caption" sx={{ color: tokens.text.secondary }}>No coordinates</Typography>
              <TextField
                size="small"
                placeholder="Search stores"
                value={unpinnedQuery}
                onChange={(event) => setUnpinnedQuery(event.target.value)}
                inputProps={{ 'aria-label': 'Search stores', 'data-testid': 'store-map-search' }}
                sx={{ mt: 0.5 }}
              />
              <Box data-testid="store-map-unpinned-scroll" sx={{ overflowY: 'auto', flex: 1, minHeight: 0, mt: 0.5 }}>
                {unpinned.length === 0 ? (
                  <Typography variant="body2" sx={{ color: tokens.text.muted }}>Every store in this view has a pin.</Typography>
                ) : listed.length === 0 ? (
                  <Typography variant="body2" sx={{ color: tokens.text.muted }}>No store matches that search.</Typography>
                ) : listed.map((store) => {
                  const key = storeKey(store);
                  const place = storePlace(store);
                  return (
                    <Box key={key} sx={{ mt: 1 }}>
                      <Typography variant="body2">
                        {place}
                        {place !== store.site_label ? (
                          <Box component="span" sx={{ color: tokens.text.secondary }}> · {store.site_label}</Box>
                        ) : null}
                        <Box component="span" sx={{ color: tokens.text.secondary }}> · {store.customer_name}</Box>
                      </Typography>
                      {store.location_suggestion?.outcome === 'manual' ? (
                        <Typography variant="caption" sx={{ display: 'block', color: tokens.text.secondary }} data-testid="place-manual">
                          {store.location_suggestion.reason === 'multiple'
                            ? 'More than one place matches. Drop a pin.'
                            : 'No place match. Drop a pin.'}
                        </Typography>
                      ) : null}
                      {pinError && pinErrorKey === key ? (
                        <Typography variant="caption" color="error" data-testid="pin-error" sx={{ display: 'block' }}>{pinError}</Typography>
                      ) : null}
                      <Button size="small" data-testid="drop-pin" onClick={() => {
                        setPinFor(key);
                        setPinError(null);
                        setPinErrorKey(null);
                      }}>Drop pin</Button>
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
                          <Button size="small" variant="contained" disabled={saving} onClick={() => void savePin(store)}>Save pin</Button>
                        </Box>
                      ) : null}
                    </Box>
                  );
                })}
              </Box>
              </Box>
            </Box>
          </MapAside>
        </MapLayout>
      )}
    </Box>
  );
}
