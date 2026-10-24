import { describe, expect, it } from 'vitest';

import { exportableSvg, imageCaption } from './exportPng';

describe('chart image framing', () => {
  it('preserves both axis units and full HTML axis names in the image caption', () => {
    const root = document.createElement('div');
    root.innerHTML = '<p data-testid="chart-axis-title-top">Support (US$)</p><p data-testid="chart-axis-title-right">Delivery (%)</p><p data-testid="chart-axis-title-bottom">Period (month)</p>';
    expect(imageCaption(root, 'Account · July')).toBe('Account · July · Support (US$) · Delivery (%) · Period (month)');
  });

  it('exports one chart drawing and explains tables or multiple drawings', () => {
    const root = document.createElement('div');
    expect(exportableSvg(root).reason).toMatch(/use CSV/);
    root.innerHTML = '<svg class="recharts-surface"></svg>';
    expect(exportableSvg(root).svg).toBe(root.querySelector('svg'));
    root.innerHTML += '<svg class="recharts-surface"></svg>';
    expect(exportableSvg(root).reason).toMatch(/more than one drawing/);
  });
});
