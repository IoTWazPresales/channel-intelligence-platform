'use client';

import type { KeyboardEvent as ReactKeyboardEvent, ReactNode } from 'react';
import { createContext, useContext, useMemo, useRef } from 'react';
import type { Layout, LayoutItem } from 'react-grid-layout';
import ReactGridLayout, { useContainerWidth, verticalCompactor } from 'react-grid-layout';

import 'react-grid-layout/css/styles.css';
import 'react-resizable/css/styles.css';

import type { DashboardWidget } from './types';

type Props = {
  widgets: DashboardWidget[];
  onLayoutPersist: (next: Array<{ id: number; layout: { x: number; y: number; w: number; h: number } }>) => void;
  renderWidget: (widget: DashboardWidget) => ReactNode;
};

/** Below this container width, widgets stack full-width. The saved 12-column layout is not rewritten. */
export const DASHBOARD_STACK_BELOW = 720;

const COLS = 12;
const MIN_W = 3;
const MIN_H = 4;

export type SavedLayout = { id: number; layout: { x: number; y: number; w: number; h: number } };

function overlaps(a: SavedLayout['layout'], b: SavedLayout['layout']) {
  return a.x < b.x + b.w && a.x + a.w > b.x && a.y < b.y + b.h && a.y + a.h > b.y;
}

/**
 * Keyboard equivalent of a drag or resize. Arrows move by one cell. Shift+arrows resize.
 * Returns null when the key is not a layout key or the box cannot move.
 */
export function nudgeLayout(items: SavedLayout[], id: number, action: string): SavedLayout[] | null {
  const current = items.find((item) => item.id === id);
  if (!current) return null;
  const box = { ...current.layout };
  if (action === 'left') box.x -= 1;
  else if (action === 'right') box.x += 1;
  else if (action === 'up') box.y -= 1;
  else if (action === 'down') box.y += 1;
  else if (action === 'wider') box.w += 1;
  else if (action === 'narrower') box.w -= 1;
  else if (action === 'taller') box.h += 1;
  else if (action === 'shorter') box.h -= 1;
  else return null;
  box.w = Math.max(MIN_W, Math.min(box.w, COLS));
  box.h = Math.max(MIN_H, box.h);
  box.x = Math.max(0, Math.min(box.x, COLS - box.w));
  box.y = Math.max(0, box.y);
  const unchanged =
    box.x === current.layout.x && box.y === current.layout.y && box.w === current.layout.w && box.h === current.layout.h;
  if (unchanged) return null;
  let placed = { ...box };
  const others = items.filter((item) => item.id !== id);
  for (let guard = 0; guard < 40 && others.some((item) => overlaps(placed, item.layout)); guard += 1) {
    placed = { ...placed, y: placed.y + 1 };
  }
  return items.map((item) => (item.id === id ? { ...item, layout: placed } : item));
}

type LayoutKeyHandler = (id: number, event: ReactKeyboardEvent) => void;
const LayoutKeyContext = createContext<LayoutKeyHandler | null>(null);

export function useDashboardLayoutKey() {
  return useContext(LayoutKeyContext);
}

export function layoutForWidth(items: LayoutItem[], width: number): LayoutItem[] {
  if (width <= 0 || width >= DASHBOARD_STACK_BELOW) return items;
  let y = 0;
  return items.map((item) => {
    const next: LayoutItem = { ...item, x: 0, y, w: 12 };
    y += item.h;
    return next;
  });
}

function itemLayout(w: DashboardWidget, index: number): LayoutItem {
  const l = w.layout_json || {};
  return {
    i: String(w.id),
    x: typeof l.x === 'number' ? l.x : (index % 2) * 6,
    y: typeof l.y === 'number' ? l.y : Math.floor(index / 2) * 8,
    w: typeof l.w === 'number' ? l.w : 6,
    h: typeof l.h === 'number' ? l.h : 8,
    minW: 3,
    minH: 4,
  };
}

export function DashboardGrid({ widgets, onLayoutPersist, renderWidget }: Props) {
  const { width, containerRef, mounted } = useContainerWidth();
  const skipMount = useRef(true);
  const persistTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const savedLayout = useMemo(() => widgets.map((w, i) => itemLayout(w, i)), [widgets]);
  const layout = useMemo(() => layoutForWidth(savedLayout, width), [savedLayout, width]);
  const stacked = width > 0 && width < DASHBOARD_STACK_BELOW;
  const onLayoutKey = (id: number, event: ReactKeyboardEvent) => {
    if (stacked) return;
    const action = (
      {
        ArrowLeft: event.shiftKey ? 'narrower' : 'left',
        ArrowRight: event.shiftKey ? 'wider' : 'right',
        ArrowUp: event.shiftKey ? 'shorter' : 'up',
        ArrowDown: event.shiftKey ? 'taller' : 'down',
      } as Record<string, string>
    )[event.key];
    if (!action) return;
    event.preventDefault();
    const next = nudgeLayout(
      savedLayout.map((item) => ({ id: Number(item.i), layout: { x: item.x, y: item.y, w: item.w, h: item.h } })),
      id,
      action,
    );
    if (next) onLayoutPersist(next);
  };

  return (
    <LayoutKeyContext.Provider value={onLayoutKey}>
      <div ref={containerRef} style={{ width: '100%' }}>
        {mounted && width > 0 && (
          <ReactGridLayout
            width={width}
            layout={layout}
            gridConfig={{ cols: 12, rowHeight: 36, margin: [12, 12] }}
            dragConfig={{ enabled: !stacked, handle: '.dashboard-widget-drag' }}
            resizeConfig={{ enabled: !stacked }}
            compactor={verticalCompactor}
            onLayoutChange={(next: Layout) => {
              if (stacked) return;
              if (skipMount.current) {
                skipMount.current = false;
                return;
              }
              if (persistTimer.current) clearTimeout(persistTimer.current);
              persistTimer.current = setTimeout(() => {
                onLayoutPersist(
                  next.map((item) => ({
                    id: Number(item.i),
                    layout: { x: item.x, y: item.y, w: item.w, h: item.h },
                  })),
                );
              }, 400);
            }}
          >
            {widgets.map((w) => (
              <div key={String(w.id)}>{renderWidget(w)}</div>
            ))}
          </ReactGridLayout>
        )}
      </div>
    </LayoutKeyContext.Provider>
  );
}
