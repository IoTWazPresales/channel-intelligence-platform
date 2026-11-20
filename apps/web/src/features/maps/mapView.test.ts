import { describe, expect, it } from 'vitest';

import { BASEMAP_BOUNDS, basemapStrokeWidth, projectMapPoint } from './mapGeometry';
import {
  MIN_VIEW_LON_SPAN,
  WORLD_BOUNDS,
  clampMapView,
  latSpanOf,
  lonSpanOf,
  panLimits,
  panMapView,
  zoomMapView,
} from './mapView';

const view = { minLat: -40, maxLat: 0, minLon: 0, maxLon: 62 };

describe('map view', () => {
  it('pans by degrees without changing the span', () => {
    const moved = panMapView(view, 10, -5);
    expect(moved).toEqual({ minLat: -45, maxLat: -5, minLon: 10, maxLon: 72 });
    expect(lonSpanOf(moved)).toBeCloseTo(lonSpanOf(view));
    expect(latSpanOf(moved)).toBeCloseTo(latSpanOf(view));
  });

  it('clamps a pan to the limits and never past the world', () => {
    const limits = { minLat: -44, maxLat: 58, minLon: -22, maxLon: 136 };
    const east = panMapView(view, 500, 0, limits);
    expect(east.maxLon).toBeCloseTo(136);
    expect(lonSpanOf(east)).toBeCloseTo(lonSpanOf(view));
    const north = panMapView(view, 0, 500, limits);
    expect(north.maxLat).toBeCloseTo(58);
    const west = panMapView(view, -500, 0);
    expect(west.minLon).toBeCloseTo(-180);
    expect(panMapView(view, 0, -500).minLat).toBeCloseTo(-90);
  });

  it('scales a view larger than the limits down, keeping its aspect', () => {
    const clamped = clampMapView({ minLat: -200, maxLat: 200, minLon: -400, maxLon: 400 });
    expect(latSpanOf(clamped)).toBeCloseTo(180);
    expect(lonSpanOf(clamped) / latSpanOf(clamped)).toBeCloseTo(800 / 400);
    expect(clamped.minLat).toBeGreaterThanOrEqual(WORLD_BOUNDS.minLat);
  });

  it('zooms around the centre, keeps the aspect and stops at the tightest span', () => {
    const closer = zoomMapView(view, 0.5);
    expect(lonSpanOf(closer)).toBeCloseTo(31);
    expect(latSpanOf(closer)).toBeCloseTo(20);
    expect((closer.minLon + closer.maxLon) / 2).toBeCloseTo(31);
    expect((closer.minLat + closer.maxLat) / 2).toBeCloseTo(-20);
    const tightest = zoomMapView(view, 0.0001);
    expect(lonSpanOf(tightest)).toBeCloseTo(MIN_VIEW_LON_SPAN);
    expect(latSpanOf(tightest) / lonSpanOf(tightest)).toBeCloseTo(latSpanOf(view) / lonSpanOf(view));
    const wider = zoomMapView(view, 1.6, BASEMAP_BOUNDS);
    expect(lonSpanOf(wider)).toBeGreaterThan(lonSpanOf(view));
  });

  it('limits panning to the basemap, the fitted view and the pins', () => {
    const fit = { minLat: -50, maxLat: -10, minLon: -40, maxLon: 22 };
    const limits = panLimits(fit, [{ latitude: 70, longitude: 150 }]);
    expect(limits).toEqual({ minLat: -50, maxLat: 70, minLon: -40, maxLon: 150 });
    const world = panLimits(fit, [{ latitude: 95, longitude: 200 }, { latitude: -95, longitude: -200 }]);
    expect(world).toEqual(WORLD_BOUNDS);
  });

  it('keeps basemap dots the same size on screen when zoomed in', () => {
    expect(basemapStrokeWidth()).toBe(2.4);
    expect(basemapStrokeWidth(BASEMAP_BOUNDS)).toBe(2.4);
    expect(basemapStrokeWidth(zoomMapView(view, 0.25))).toBeLessThan(2.4);
    // Zooming out past the basemap never makes the dots bigger.
    expect(basemapStrokeWidth(WORLD_BOUNDS)).toBe(2.4);
  });

  it('projects a pin identically for the same view whatever panned it there', () => {
    const point = { latitude: -20, longitude: 30 };
    const panned = panMapView(view, 8, 3);
    const back = panMapView(panned, -8, -3);
    expect(projectMapPoint(point, back).x).toBeCloseTo(projectMapPoint(point, view).x);
    expect(projectMapPoint(point, back).y).toBeCloseTo(projectMapPoint(point, view).y);
  });
});
