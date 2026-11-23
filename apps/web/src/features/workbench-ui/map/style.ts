import type { StyleSpecification, VectorSourceSpecification } from 'maplibre-gl';

import { tokensFor } from '@/theme/cipTokens';

export type MapSettings = {
  tilejsonUrl?: string;
  glyphsUrl?: string;
  attribution?: string;
};

export type WorkbenchMapStyle = StyleSpecification & {
  metadata: { 'workbench:attribution': string };
};

export const DOT_IMAGE = 'workbench-land-dot';

export type MapThemeMode = 'light' | 'dark';

export function mapColorsFor(mode: MapThemeMode = 'dark') {
  const t = tokensFor(mode);
  return mode === 'dark'
    ? {
        panel: '#121519',
        land: '#18222c',
        landcover: t.bg.surfaceMuted,
        road: t.text.muted,
        building: t.border.strong,
        text: t.text.secondary,
      }
    : {
        panel: '#f6f9fb',
        land: '#e6eef3',
        landcover: t.bg.surfaceMuted,
        road: t.text.muted,
        building: t.border.strong,
        text: t.text.secondary,
      };
}

export const mapColors = mapColorsFor('dark');

/** Always retained, including when a tenant supplies additional provider attribution. */
export const OSM_ATTRIBUTION =
  '<a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener noreferrer">© OpenStreetMap contributors</a>';

function escapeHtml(text: string): string {
  return text.replace(/[&<>"']/g, (character) => ({
    '&': '&amp;',
    '<': '&lt;',
    '>': '&gt;',
    '"': '&quot;',
    "'": '&#39;',
  })[character]!);
}

export function mapAttribution(settings: MapSettings): string {
  const provider = settings.attribution?.trim();
  return provider ? `${OSM_ATTRIBUTION} | ${escapeHtml(provider)}` : OSM_ATTRIBUTION;
}

/**
 * The future PMTiles seam is this source factory. Register the protocol before constructing
 * a map, then add a separate pmtiles setting/source choice here. A PMTiles archive must never
 * be silently treated as TileJSON. No pmtiles dependency or setting is advertised yet.
 */
function vectorSource(tilejsonUrl: string): VectorSourceSpecification {
  // Leave source attribution to TileJSON so provider/OpenMapTiles attribution is also retained.
  return { type: 'vector', url: tilejsonUrl };
}

/** Same cool dot colour/opacity as the shared SVG MapCanvas, generated without canvas APIs. */
export function dotImage(mode: MapThemeMode = 'dark'): { width: number; height: number; data: Uint8Array } {
  // 4px tile (was 8px): tighter land stipple that still matches the SVG basemap's cool grey dots.
  const width = 4;
  const height = 4;
  const data = new Uint8Array(width * height * 4);
  const rgba: [number, number, number, number] = mode === 'dark' ? [160, 185, 205, 90] : [40, 70, 95, 96];
  for (let y = 0; y < height; y += 1) {
    for (let x = 0; x < width; x += 1) {
      if ((x - 1.5) ** 2 + (y - 1.5) ** 2 > 1.05) continue;
      data.set(rgba, (y * width + x) * 4);
    }
  }
  return { width, height, data };
}

/** OpenMapTiles schema; geography and provider URLs come entirely from tenant configuration. */
export function buildMapStyle(settings: MapSettings, mode: MapThemeMode = 'dark'): WorkbenchMapStyle | null {
  const url = settings.tilejsonUrl?.trim();
  if (!url) return null;
  const colors = mapColorsFor(mode);

  const style: WorkbenchMapStyle = {
    version: 8,
    name: mode === 'dark' ? 'Workbench dark' : 'Workbench light',
    metadata: { 'workbench:attribution': mapAttribution(settings) },
    sources: { openmaptiles: vectorSource(url) },
    layers: [
      {
        id: 'land',
        type: 'background',
        paint: {
          'background-color': [
            'interpolate', ['linear'], ['zoom'],
            5, colors.panel,
            10, colors.land,
          ],
        },
      },
      {
        // OpenMapTiles has no complete "land" polygon layer. A patterned background, masked
        // by the water polygons below, covers deserts and other land without landcover tags.
        id: 'dotted-land',
        type: 'background',
        paint: {
          'background-pattern': DOT_IMAGE,
          'background-opacity': ['interpolate', ['linear'], ['zoom'], 6, 1, 10, 0],
        },
      },
      {
        id: 'landcover',
        type: 'fill',
        source: 'openmaptiles',
        'source-layer': 'landcover',
        minzoom: 6,
        paint: {
          'fill-color': colors.landcover,
          'fill-opacity': ['interpolate', ['linear'], ['zoom'], 6, 0, 10, 0.35],
        },
      },
      {
        id: 'landuse',
        type: 'fill',
        source: 'openmaptiles',
        'source-layer': 'landuse',
        minzoom: 8,
        paint: {
          'fill-color': colors.landcover,
          'fill-opacity': ['interpolate', ['linear'], ['zoom'], 8, 0, 12, 0.5],
        },
      },
      {
        id: 'water',
        type: 'fill',
        source: 'openmaptiles',
        'source-layer': 'water',
        paint: { 'fill-color': colors.panel },
      },
      {
        id: 'transportation',
        type: 'line',
        source: 'openmaptiles',
        'source-layer': 'transportation',
        minzoom: 8,
        layout: { 'line-cap': 'round', 'line-join': 'round' },
        paint: {
          'line-color': colors.road,
          'line-opacity': ['interpolate', ['linear'], ['zoom'], 8, 0, 12, 0.9],
          'line-width': [
            'interpolate', ['linear'], ['zoom'],
            8, 0.4,
            12, 1,
            17, 4,
          ],
        },
      },
      {
        id: 'building',
        type: 'fill',
        source: 'openmaptiles',
        'source-layer': 'building',
        minzoom: 13,
        paint: {
          'fill-color': colors.building,
          'fill-opacity': ['interpolate', ['linear'], ['zoom'], 13, 0, 16, 0.9],
        },
      },
    ],
  };

  const glyphs = settings.glyphsUrl?.trim();
  if (glyphs) {
    style.glyphs = glyphs;
    for (const [id, sourceLayer, minzoom] of [
      ['place-labels', 'place', 3],
      ['road-labels', 'transportation_name', 13],
      ['poi-labels', 'poi', 14],
    ] as const) {
      style.layers.push({
        id,
        type: 'symbol',
        source: 'openmaptiles',
        'source-layer': sourceLayer,
        minzoom,
        layout: {
          'symbol-placement': sourceLayer === 'transportation_name' ? 'line' : 'point',
          'text-field': ['coalesce', ['get', 'name'], ['get', 'name:latin'], ''],
          'text-font': ['Noto Sans Regular'],
          'text-size': ['interpolate', ['linear'], ['zoom'], 3, 10, 16, 13],
          'text-max-width': 9,
          'text-padding': 5,
        },
        paint: {
          'text-color': colors.text,
          'text-halo-color': colors.panel,
          'text-halo-width': 1.5,
        },
      });
    }
  }
  return style;
}
