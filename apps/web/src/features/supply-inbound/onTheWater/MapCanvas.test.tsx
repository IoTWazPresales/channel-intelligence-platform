import { createTheme, ThemeProvider } from '@mui/material/styles';
import { screen, within } from '@testing-library/react';
import { createRef } from 'react';
import { describe, expect, it, vi } from 'vitest';

import { renderWithProviders } from '@/test-utils/renderWithProviders';

import { BASEMAP_DOTS } from '@/features/maps/basemapDots';
import { MapCanvas, MapPanel } from '@/features/maps/MapCanvas';
import { mapBoundsForPoints, mapViewBox } from '@/features/maps/mapGeometry';

describe('shared map canvas', () => {
  it.each(['light', 'dark'] as const)('keeps the Shipments basemap theme in %s mode', (mode) => {
    renderWithProviders(
      <ThemeProvider theme={createTheme({ palette: { mode } })}>
        <MapPanel>
          <MapCanvas data-testid="canvas" label="Map" svgChildren={<path data-testid="lane" d="M0 0L10 10" />}>
            <button type="button">Pin</button>
          </MapCanvas>
        </MapPanel>
      </ThemeProvider>,
    );
    const canvas = screen.getByTestId('canvas');
    const svg = within(canvas).getByRole('img', { name: 'Map' });
    expect(svg).toHaveAttribute('viewBox', '0 0 1000 646');
    expect(svg.querySelector('path')).toHaveAttribute('d', BASEMAP_DOTS);
    expect(svg.querySelector('path')).toHaveAttribute('stroke',
      mode === 'dark' ? 'rgba(160,185,205,0.28)' : 'rgba(40,70,95,0.30)');
    expect(within(svg).getByTestId('lane')).toBeInTheDocument();
    expect(within(canvas).getByRole('button', { name: 'Pin' })).toBeInTheDocument();
    expect(getComputedStyle(canvas).aspectRatio).toMatch(/^1000\s*\/\s*646$/);
    expect(getComputedStyle(canvas).position).toBe('relative');
    expect(getComputedStyle(canvas).overflow).toBe('hidden');
  });

  it('forwards the canvas ref, measures it, and disconnects its observer', () => {
    const disconnect = vi.fn();
    const observe = vi.fn();
    const onSizeChange = vi.fn();
    class Observer {
      observe = observe;
      disconnect = disconnect;
    }
    vi.stubGlobal('ResizeObserver', Observer);
    const width = vi.spyOn(HTMLElement.prototype, 'clientWidth', 'get').mockReturnValue(800);
    const height = vi.spyOn(HTMLElement.prototype, 'clientHeight', 'get').mockReturnValue(516.8);
    try {
      const ref = createRef<HTMLDivElement>();
      const { unmount } = renderWithProviders(
        <MapCanvas ref={ref} data-testid="canvas" label="Map" onSizeChange={onSizeChange} />,
      );
      expect(ref.current).toBe(screen.getByTestId('canvas'));
      expect(observe).toHaveBeenCalledWith(ref.current);
      expect(onSizeChange).toHaveBeenCalledWith({ w: 800, h: 516.8 });
      unmount();
      expect(disconnect).toHaveBeenCalledOnce();
    } finally {
      width.mockRestore();
      height.mockRestore();
      vi.unstubAllGlobals();
    }
  });

  it('changes only the viewBox when pins fall outside the existing extent', () => {
    const bounds = mapBoundsForPoints([{ latitude: 70, longitude: -100 }]);
    renderWithProviders(<MapCanvas data-testid="canvas" label="Map" bounds={bounds} />);
    const canvas = screen.getByTestId('canvas');
    expect(within(canvas).getByRole('img')).toHaveAttribute('viewBox', mapViewBox(bounds));
    expect(getComputedStyle(canvas).aspectRatio).toMatch(/^1000\s*\/\s*646$/);
    expect(canvas.querySelector('svg > path')).toHaveAttribute('d', BASEMAP_DOTS);
  });
});
