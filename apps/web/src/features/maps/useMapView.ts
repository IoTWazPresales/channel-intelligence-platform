'use client';

import { useRef, useState } from 'react';
import type { PointerEvent, RefObject } from 'react';

import type { MapBounds } from './mapGeometry';
import { latSpanOf, lonSpanOf, panMapView, zoomMapView } from './mapView';

const ZOOM_STEP = 1.6;
// A click that wobbles a pixel or two is still a click.
const PAN_THRESHOLD_PX = 3;

type Gesture = {
  pointerId: number;
  clientX: number;
  clientY: number;
  start: MapBounds;
  width: number;
  height: number;
  moved: boolean;
};

/**
 * The visible window of a map. Until the steward pans or zooms it follows `fit`; after that it is
 * their own view (kept inside `limits`) until they reset it. Only the view changes, never data.
 */
export function useMapView(
  fit: MapBounds,
  limits: MapBounds,
  canvasRef: RefObject<HTMLElement | null>
) {
  const [view, setView] = useState<MapBounds | null>(null);
  const [grabbing, setGrabbing] = useState(false);
  const gesture = useRef<Gesture | null>(null);
  const bounds = view ?? fit;

  const zoomedIn = zoomMapView(bounds, 1 / ZOOM_STEP, limits);
  const zoomedOut = zoomMapView(bounds, ZOOM_STEP, limits);

  function onPointerDown(event: PointerEvent<HTMLElement>) {
    if (event.button !== 0 || gesture.current) return;
    // Pins, buttons and panels keep their own behaviour; only the map background pans.
    const target = event.target as Element | null;
    if (target?.closest?.('button, a, input, [data-no-pan]')) return;
    const rect = canvasRef.current?.getBoundingClientRect();
    if (!rect?.width || !rect.height) return;
    gesture.current = {
      pointerId: event.pointerId,
      clientX: event.clientX,
      clientY: event.clientY,
      start: bounds,
      width: rect.width,
      height: rect.height,
      moved: false,
    };
    event.currentTarget.setPointerCapture?.(event.pointerId);
  }

  function onPointerMove(event: PointerEvent<HTMLElement>) {
    const drag = gesture.current;
    if (!drag || event.pointerId !== drag.pointerId) return;
    const dx = event.clientX - drag.clientX;
    const dy = event.clientY - drag.clientY;
    if (!drag.moved && Math.hypot(dx, dy) < PAN_THRESHOLD_PX) return;
    if (!drag.moved) {
      drag.moved = true;
      setGrabbing(true);
    }
    // Dragging the map right shows what lies to the west; down shows what lies to the north.
    setView(
      panMapView(
        drag.start,
        -(dx / drag.width) * lonSpanOf(drag.start),
        (dy / drag.height) * latSpanOf(drag.start),
        limits
      )
    );
  }

  function endGesture(event: PointerEvent<HTMLElement>) {
    if (gesture.current?.pointerId !== event.pointerId) return;
    gesture.current = null;
    setGrabbing(false);
    if (event.currentTarget.hasPointerCapture?.(event.pointerId)) {
      event.currentTarget.releasePointerCapture(event.pointerId);
    }
  }

  return {
    bounds,
    panned: view !== null,
    grabbing,
    canZoomIn: lonSpanOf(zoomedIn) < lonSpanOf(bounds) - 1e-9,
    canZoomOut: lonSpanOf(zoomedOut) > lonSpanOf(bounds) + 1e-9,
    zoomIn: () => setView(zoomedIn),
    zoomOut: () => setView(zoomedOut),
    reset: () => setView(null),
    panHandlers: {
      onPointerDown,
      onPointerMove,
      onPointerUp: endGesture,
      onPointerCancel: endGesture,
    },
  };
}
