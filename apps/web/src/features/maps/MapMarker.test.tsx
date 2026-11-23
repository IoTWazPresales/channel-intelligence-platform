import { screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { renderWithProviders } from '@/test-utils/renderWithProviders';

import { MapMarker, markerAlpha } from './MapMarker';

describe('shared map marker', () => {
  it('draws the Shipments marker: a 44px target around a filled dot', () => {
    renderWithProviders(<MapMarker x={25} y={40} color="#1f8" aria-label="Vessel">3</MapMarker>);
    const marker = screen.getByRole('button', { name: 'Vessel' });
    expect(getComputedStyle(marker).width).toBe('44px');
    expect(getComputedStyle(marker).left).toBe('25%');
    expect(getComputedStyle(marker).top).toBe('40%');
    expect(getComputedStyle(marker).transform).toBe('translate(-50%, -50%)');
    const dot = marker.querySelector('[data-marker-dot]') as HTMLElement;
    expect(dot).toHaveTextContent('3');
    expect(dot).toHaveAttribute('data-hollow', 'false');
    expect(getComputedStyle(dot).width).toBe('11px');
    expect(getComputedStyle(dot).borderRadius).toBe('50%');
  });

  it('draws a proposal hollow and dashed in its own colour, and nudges it on screen only', () => {
    renderWithProviders(
      <MapMarker x={10} y={10} color="rgb(10, 20, 30)" hollow offset={{ dx: 6, dy: -4 }} hit={22} aria-label="Pin" />,
    );
    const marker = screen.getByRole('button', { name: 'Pin' });
    expect(getComputedStyle(marker).width).toBe('22px');
    expect(getComputedStyle(marker).transform).toBe('translate(calc(-50% + 6px), calc(-50% + -4px))');
    const dot = marker.querySelector('[data-marker-dot]') as HTMLElement;
    expect(dot).toHaveAttribute('data-hollow', 'true');
    expect(getComputedStyle(dot).borderStyle).toBe('dashed');
    expect(getComputedStyle(dot).backgroundColor).toMatch(/^(transparent|rgba\(0, 0, 0, 0\))$/);
  });

  it('draws a proposed pin as a filled dot with the same soft glow as Shipments', () => {
    renderWithProviders(
      <MapMarker x={15} y={20} color="rgb(10, 20, 30)" proposed aria-label="Proposed Pin">5</MapMarker>,
    );
    const marker = screen.getByRole('button', { name: 'Proposed Pin' });
    const dot = marker.querySelector('[data-marker-dot]') as HTMLElement;
    expect(dot).toHaveAttribute('data-hollow', 'false');
    expect(dot).toHaveAttribute('data-proposed', 'true');
    expect(dot).toHaveTextContent('5');
    expect(getComputedStyle(dot).backgroundColor).toBe('rgb(10, 20, 30)');
    expect(getComputedStyle(dot).outlineStyle).not.toBe('dashed');
    expect(getComputedStyle(dot).boxShadow).toContain('18px');
  });

  it('fades a color-mix() sell-through colour as well as a plain one', () => {
    const ramp = 'color-mix(in srgb, #0a0 60%, #a00)';
    expect(markerAlpha(ramp, 0.18)).toBe(`color-mix(in srgb, ${ramp} 18%, transparent)`);
    expect(markerAlpha('#ff0000', 0.5)).toMatch(/^rgba\(255, 0, 0, 0\.5\)$/);
    expect(() =>
      renderWithProviders(<MapMarker x={1} y={1} color={ramp} selected aria-label="Ramp" />),
    ).not.toThrow();
  });
});
