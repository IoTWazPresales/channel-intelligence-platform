'use client';

import 'maplibre-gl/dist/maplibre-gl.css';

import { Alert, Box, Link, Typography } from '@mui/material';
import { alpha, useTheme } from '@mui/material/styles';
import type { GeoJSONSource, Map as LibreMap } from 'maplibre-gl';
import {
  useEffect,
  useMemo,
  useRef,
  useState,
  type PointerEvent,
  type ReactNode,
} from 'react';

import { MAP_ASPECT_RATIO } from '@/features/maps/mapGeometry';
import { MapMarker } from '@/features/maps/MapMarker';
import { tokensFor } from '@/theme/cipTokens';
import { safeDisplayError } from '@/lib/api';

import {
  POINT_SOURCE,
  clusterSource,
  pointBounds,
  pointCollection,
  sourceMarkers,
  wrapLongitude,
  type Coordinates,
  type SourceMarker,
  type WorkbenchPoint,
} from './clustering';
import {
  DOT_IMAGE,
  buildMapStyle,
  dotImage,
  mapColorsFor,
  type MapSettings,
} from './style';

type Overlay = SourceMarker & { x: number; y: number; dx: number; dy: number };

type Props = {
  settings: MapSettings;
  points: readonly WorkbenchPoint[];
  /** Change for a new filter/data scope, not for a staged coordinate edit. */
  fitKey: string;
  selectedKey: string | null;
  onSelect: (id: string) => void;
  colorForScore: (score: number | null) => string;
  renderHover?: (id: string) => ReactNode;
  onAdjust?: (id: string, coordinates: Coordinates) => void;
  onAdjustEnd?: (id: string, coordinates: Coordinates) => void;
  canDrag?: (id: string) => boolean;
  placing?: boolean;
  onPlace?: (coordinates: Coordinates) => void;
  label?: string;
};

/**
 * Shared engine and clustered marker surface. Domain data, filters, legends, details and
 * confirmation remain with callers. This component never calls a persistence endpoint.
 */
export function WorkbenchMap(props: Props) {
  const {
    settings: { tilejsonUrl, glyphsUrl, attribution },
    selectedKey,
    fitKey,
  } = props;
  const theme = useTheme();
  const mode = theme.palette.mode;
  const t = tokensFor(mode);
  const colors = mapColorsFor(mode);
  const latest = useRef(props);
  latest.current = props;

  const container = useRef<HTMLDivElement>(null);
  const mapRef = useRef<LibreMap | null>(null);
  const redraw = useRef<() => void>(() => undefined);
  const drag = useRef<{ id: string; pointerId: number; panWasEnabled: boolean; moved: boolean } | null>(null);
  const [ready, setReady] = useState(false);
  const [overlays, setOverlays] = useState<Overlay[]>([]);
  const [hover, setHover] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const style = useMemo(
    () => buildMapStyle({ tilejsonUrl, glyphsUrl, attribution }, mode),
    [tilejsonUrl, glyphsUrl, attribution, mode],
  );
  const dataKey = JSON.stringify(pointCollection(props.points));

  function reset() {
    const map = mapRef.current;
    if (!map) return;
    const bounds = pointBounds(latest.current.points);
    if (bounds) {
      map.fitBounds(bounds, { padding: 48, maxZoom: 7.5, duration: 600 });
    } else {
      // Neutral world view: no tenant country or fallback continent.
      map.easeTo({ center: [0, 0], zoom: 0, bearing: 0, pitch: 0 });
    }
  }

  useEffect(() => {
    if (!style || !container.current) return;
    let disposed = false;
    let map: LibreMap | null = null;
    let observer: ResizeObserver | undefined;
    setReady(false);
    setError(null);
    setOverlays([]);

    async function initialise() {
      try {
        const library = await import('maplibre-gl');
        if (disposed || !container.current || !style) return;
        const instance = new library.Map({
          container: container.current,
          style,
          attributionControl: false,
          maxZoom: 20,
          renderWorldCopies: true,
        });
        map = instance;
        mapRef.current = instance;
        instance.addControl(new library.NavigationControl({ showCompass: false }), 'top-right');
        instance.addControl(new library.AttributionControl({
          compact: true,
          customAttribution: style.metadata['workbench:attribution'],
        }), 'bottom-right');
        instance.getCanvas().setAttribute('aria-label', latest.current.label ?? 'Interactive map');

        const addDots = () => {
          if (instance.hasImage(DOT_IMAGE)) instance.removeImage?.(DOT_IMAGE);
          instance.addImage(DOT_IMAGE, dotImage(mode));
        };
        instance.on('styleimagemissing', (event) => {
          if (event.id === DOT_IMAGE) addDots();
        });

        const refresh = () => {
          if (disposed || !instance.getSource(POINT_SOURCE)) return;
          const current = latest.current;
          const markers = sourceMarkers(instance.querySourceFeatures(POINT_SOURCE));
          const selected = current.points.find((point) => point.id === current.selectedKey);
          if (selected) {
            const index = markers.findIndex((marker) => marker.pointId === selected.id);
            const marker: SourceMarker = {
              ...selected,
              key: `point:${selected.id}`,
              pointId: selected.id,
              count: 1,
            };
            if (index < 0) markers.push(marker);
            else markers[index] = marker;
          }
          const element = instance.getContainer();
          const width = element.clientWidth || 800;
          const height = element.clientHeight || 480;
          const centre = instance.getCenter().lng;
          const projected = markers.map((marker) => {
            const longitude = marker.longitude + Math.round((centre - marker.longitude) / 360) * 360;
            const pixel = instance.project([longitude, marker.latitude]);
            return { ...marker, x: pixel.x / width * 100, y: pixel.y / height * 100, dx: 0, dy: 0 };
          }).filter((marker) => marker.x > -5 && marker.x < 105 && marker.y > -5 && marker.y < 105);

          // Exact co-locations cannot geographically split. At street zoom, fan their display
          // positions only; dragging still uses the underlying map coordinates.
          if (instance.getZoom() > 14) {
            const coincident = new Map<string, Overlay[]>();
            for (const marker of projected) {
              if (!marker.pointId) continue;
              const key = `${marker.x.toFixed(3)}:${marker.y.toFixed(3)}`;
              const group = coincident.get(key) ?? [];
              group.push(marker);
              coincident.set(key, group);
            }
            for (const group of coincident.values()) {
              if (group.length < 2) continue;
              group.sort((a, b) => a.key.localeCompare(b.key));
              group.forEach((marker, index) => {
                const angle = index / group.length * Math.PI * 2;
                marker.dx = Math.cos(angle) * 16;
                marker.dy = Math.sin(angle) * 16;
              });
            }
          }
          setOverlays(projected);
        };
        redraw.current = refresh;

        instance.on('load', () => {
          if (disposed) return;
          addDots();
          instance.addSource(POINT_SOURCE, clusterSource(latest.current.points));
          // A transparent layer keeps clustered source tiles active; React renders the existing
          // Shipments marker visuals, accessible buttons and numbered circles above the canvas.
          instance.addLayer({
            id: 'workbench-point-source',
            type: 'circle',
            source: POINT_SOURCE,
            paint: { 'circle-radius': 1, 'circle-opacity': 0 },
          });
          setReady(true);
          refresh();
        });
        instance.on('move', refresh);
        instance.on('sourcedata', (event) => {
          if (event.sourceId === POINT_SOURCE) refresh();
        });
        instance.on('click', (event) => {
          if (latest.current.placing) {
            latest.current.onPlace?.({
              latitude: event.lngLat.lat,
              longitude: wrapLongitude(event.lngLat.lng),
            });
          }
        });
        instance.on('error', (event) => {
          if (!disposed) setError(safeDisplayError(event.error));
        });
        observer = new ResizeObserver(() => instance.resize());
        observer.observe(instance.getContainer());
      } catch (cause) {
        if (!disposed) setError(`Map could not start: ${safeDisplayError(cause)}`);
      }
    }

    void initialise();
    return () => {
      disposed = true;
      observer?.disconnect();
      drag.current = null;
      redraw.current = () => undefined;
      if (mapRef.current === map) mapRef.current = null;
      map?.remove();
    };
  }, [style, mode]);

  useEffect(() => {
    const source = mapRef.current?.getSource(POINT_SOURCE) as GeoJSONSource | undefined;
    if (!ready || !source) return;
    const collection: ReturnType<typeof pointCollection> = JSON.parse(dataKey);
    source.setData(collection);
    redraw.current();
  }, [dataKey, ready]);

  useEffect(() => {
    if (!ready) return;
    const map = mapRef.current;
    const bounds = pointBounds(latest.current.points);
    if (map && bounds) map.fitBounds(bounds, { padding: 48, maxZoom: 7.5, duration: 600 });
  }, [fitKey, ready]);

  useEffect(() => {
    if (!ready || !selectedKey) return;
    const point = latest.current.points.find((item) => item.id === selectedKey);
    if (point) {
      mapRef.current?.flyTo({
        center: [point.longitude, point.latitude],
        zoom: 15,
        duration: 700,
      });
    }
    redraw.current();
  }, [selectedKey, ready]);

  function coordinatesFromPointer(event: PointerEvent<HTMLButtonElement>): Coordinates | null {
    const map = mapRef.current;
    if (!map) return null;
    const rect = map.getContainer().getBoundingClientRect();
    const position = map.unproject([event.clientX - rect.left, event.clientY - rect.top]);
    return { latitude: position.lat, longitude: wrapLongitude(position.lng) };
  }

  function adjust(event: PointerEvent<HTMLButtonElement>) {
    const active = drag.current;
    if (!active || active.pointerId !== event.pointerId) return;
    const coordinates = coordinatesFromPointer(event);
    if (!coordinates) return;
    active.moved = true;
    latest.current.onAdjust?.(active.id, coordinates);
  }

  function finishDrag(event: PointerEvent<HTMLButtonElement>, cancelled = false) {
    const active = drag.current;
    if (!active || active.pointerId !== event.pointerId) return;
    const coordinates = cancelled || !active.moved ? null : coordinatesFromPointer(event);
    if (coordinates) {
      latest.current.onAdjust?.(active.id, coordinates);
      latest.current.onAdjustEnd?.(active.id, coordinates);
    }
    if (active.panWasEnabled) mapRef.current?.dragPan.enable();
    drag.current = null;
    if (event.currentTarget.hasPointerCapture?.(event.pointerId)) {
      event.currentTarget.releasePointerCapture(event.pointerId);
    }
  }

  async function expand(marker: SourceMarker) {
    const map = mapRef.current;
    const source = map?.getSource(POINT_SOURCE) as GeoJSONSource | undefined;
    if (!map || !source || marker.clusterId == null) return;
    try {
      const zoom = await source.getClusterExpansionZoom(marker.clusterId);
      if (mapRef.current === map) {
        map.easeTo({ center: [marker.longitude, marker.latitude], zoom, duration: 600 });
      }
    } catch (cause) {
      if (mapRef.current === map) setError(safeDisplayError(cause));
    }
  }

  if (!style) {
    return (
      <Box data-testid="workbench-map-not-configured" sx={{ p: 3 }}>
        <Typography variant="body2">Map tiles are not configured.</Typography>
        <Link href="/settings#map-settings">Settings &gt; Map</Link>
      </Box>
    );
  }

  return (
    <Box data-testid="workbench-map">
      {!glyphsUrl?.trim() ? (
        <Alert severity="info" sx={{ mb: 1 }}>
          Map labels are not configured. Set the glyph URL in{' '}
          <Link href="/settings#map-settings">Settings &gt; Map</Link>.
        </Alert>
      ) : null}
      {error ? <Alert severity="error" sx={{ mb: 1 }}>Map could not load: {error}</Alert> : null}
      <Box
        data-map-canvas
        sx={{
          position: 'relative',
          width: '100%',
          aspectRatio: MAP_ASPECT_RATIO,
          overflow: 'hidden',
          borderRadius: 1,
          bgcolor: colors.panel,
          '& .maplibregl-ctrl-top-right': { top: 8, right: 8, margin: 0 },
          '& .maplibregl-ctrl-top-right .maplibregl-ctrl-group': {
            margin: 0,
            bgcolor: t.bg.elevated,
            border: `1px solid ${t.border.strong}`,
            borderRadius: 1,
            boxShadow: 'none',
            overflow: 'hidden',
          },
          '& .maplibregl-ctrl-group button': {
            width: 28,
            height: 28,
            bgcolor: 'transparent',
            borderColor: t.border.subtle,
          },
          '& .maplibregl-ctrl-group button:hover': { bgcolor: t.bg.surfaceMuted },
          '& .maplibregl-ctrl-group button + button': { borderTop: `1px solid ${t.border.subtle}` },
          '& .maplibregl-ctrl-group button .maplibregl-ctrl-icon': {
            filter: mode === 'dark' ? 'invert(1) brightness(1.6)' : 'none',
          },
          '& .maplibregl-ctrl-bottom-right': { bottom: 8, right: 8, margin: 0 },
          '& .maplibregl-ctrl-attrib': {
            margin: 0,
            bgcolor: alpha(t.bg.default, 0.8),
            color: t.text.secondary,
            border: `1px solid ${t.border.subtle}`,
            borderRadius: '12px',
            fontSize: 11,
            boxShadow: 'none',
          },
          '& .maplibregl-ctrl-attrib.maplibregl-compact': { minHeight: 24 },
          '& .maplibregl-ctrl-attrib a': { color: t.accent.primary },
          '& .maplibregl-ctrl-attrib-button': {
            bgcolor: 'transparent',
            filter: mode === 'dark' ? 'invert(0.85)' : 'none',
          },
        }}
        onKeyDown={(event) => {
          const map = mapRef.current;
          if (event.key !== 'Enter' || !props.placing || !map || event.target !== map.getCanvas()) return;
          event.preventDefault();
          const centre = map.getCenter();
          props.onPlace?.({ latitude: centre.lat, longitude: wrapLongitude(centre.lng) });
        }}
      >
        <Box ref={container} data-testid="workbench-map-engine" sx={{ position: 'absolute', inset: 0 }} />
        <Box
          component="button"
          type="button"
          data-testid="map-reset-view"
          disabled={!ready}
          onClick={reset}
          sx={{
            position: 'absolute',
            top: 8,
            right: 42,
            zIndex: 3,
            minWidth: 28,
            height: 28,
            px: 1,
            font: 'inherit',
            fontSize: 12,
            fontWeight: 600,
            color: t.text.primary,
            bgcolor: t.bg.elevated,
            border: `1px solid ${t.border.strong}`,
            borderRadius: 1,
            cursor: 'pointer',
            '&:disabled': { cursor: 'default', opacity: 0.45 },
          }}
        >
          Reset view
        </Box>
        {!ready && !error ? (
          <Typography
            variant="caption"
            sx={{
              position: 'absolute',
              top: 8,
              left: 8,
              zIndex: 3,
              px: 1,
              py: 0.25,
              borderRadius: 1,
              bgcolor: alpha(t.bg.default, 0.8),
              color: t.text.secondary,
            }}
          >
            Loading map…
          </Typography>
        ) : null}
        {overlays.map((marker) => {
          const point = props.points.find((item) => item.id === marker.pointId);
          const selected = marker.pointId === props.selectedKey;
          const size = marker.clusterId == null
            ? (selected ? 16 : 11)
            : 16 + (String(marker.count).length - 1) * 5;
          const color = props.colorForScore(marker.score);
          return (
            <MapMarker
              key={marker.key}
              x={marker.x}
              y={marker.y}
              offset={{ dx: marker.dx, dy: marker.dy }}
              hit={32}
              color={color}
              size={size}
              selected={selected}
              proposed={marker.proposed}
              glow={marker.clusterId == null}
              zIndex={selected ? 2 : 1}
              cursor={point && props.onAdjust && (props.canDrag?.(point.id) ?? point.proposed) ? 'grab' : 'pointer'}
              touchAction={point && props.onAdjust && (props.canDrag?.(point.id) ?? point.proposed) ? 'none' : 'auto'}
              data-testid={marker.clusterId == null ? 'workbench-map-pin' : 'workbench-map-cluster'}
              data-point-id={marker.pointId}
              data-pin-state={marker.proposed ? 'proposed' : 'confirmed'}
              aria-label={point ? `${point.label} pin` : `${marker.count} locations. Zoom in.`}
              aria-pressed={marker.pointId ? selected : undefined}
              onMouseEnter={() => setHover(marker.pointId ?? null)}
              onMouseLeave={() => setHover(null)}
              onFocus={() => setHover(marker.pointId ?? null)}
              onBlur={() => setHover(null)}
              onClick={(event) => {
                event.stopPropagation();
                if (marker.clusterId != null) void expand(marker);
                else if (marker.pointId) props.onSelect(marker.pointId);
              }}
              onPointerDown={(event) => {
                if (!point || !props.onAdjust || event.button !== 0) return;
                if (!(props.canDrag?.(point.id) ?? point.proposed)) return;
                event.stopPropagation();
                event.preventDefault();
                const map = mapRef.current;
                if (!map) return;
                props.onSelect(point.id);
                drag.current = {
                  id: point.id,
                  pointerId: event.pointerId,
                  panWasEnabled: map.dragPan.isEnabled(),
                  moved: false,
                };
                map.dragPan.disable();
                event.currentTarget.setPointerCapture?.(event.pointerId);
              }}
              onPointerMove={adjust}
              onPointerUp={(event) => finishDrag(event)}
              onPointerCancel={(event) => finishDrag(event, true)}
              onLostPointerCapture={(event) => finishDrag(event, true)}
            >
              {marker.clusterId != null ? marker.count : null}
            </MapMarker>
          );
        })}
        {hover && props.renderHover ? (
          <Box
            data-testid="workbench-map-hover"
            sx={{
              position: 'absolute', left: 8, bottom: 8, zIndex: 3,
              maxWidth: '85%', p: 1.25, borderRadius: 1.25,
              bgcolor: alpha(t.bg.default, 0.96), color: t.text.primary,
              border: `1px solid ${t.border.subtle}`,
              boxShadow: '0 8px 24px rgba(0,0,0,0.28)', pointerEvents: 'none',
            }}
          >
            {props.renderHover(hover)}
          </Box>
        ) : null}
      </Box>
    </Box>
  );
}
