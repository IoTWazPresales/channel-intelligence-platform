'use client';

import type { ReactNode } from 'react';
import type { Layout, LayoutItem } from 'react-grid-layout';
import ReactGridLayout, { useContainerWidth, verticalCompactor } from 'react-grid-layout';
import { useMemo, useRef } from 'react';

import 'react-grid-layout/css/styles.css';
import 'react-resizable/css/styles.css';

import type { DashboardWidget } from './types';

type Props = {
  widgets: DashboardWidget[];
  onLayoutPersist: (next: Array<{ id: number; layout: { x: number; y: number; w: number; h: number } }>) => void;
  renderWidget: (widget: DashboardWidget) => ReactNode;
};

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
  const layout = useMemo(() => widgets.map((w, i) => itemLayout(w, i)), [widgets]);

  return (
    <div ref={containerRef} style={{ width: '100%' }}>
      {mounted && width > 0 && (
        <ReactGridLayout
          width={width}
          layout={layout}
          gridConfig={{ cols: 12, rowHeight: 36, margin: [12, 12] }}
          dragConfig={{ enabled: true, handle: '.dashboard-widget-drag' }}
          resizeConfig={{ enabled: true }}
          compactor={verticalCompactor}
          onLayoutChange={(next: Layout) => {
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
                }))
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
  );
}
