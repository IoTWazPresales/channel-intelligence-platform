import { describe, expect, it } from 'vitest';

import { stockLensFromLocation } from './StockChrome';

describe('stockLensFromLocation', () => {
  it('maps production routes onto the lab stock lenses', () => {
    expect(stockLensFromLocation('/stock', new URLSearchParams())).toBe('cover');
    expect(stockLensFromLocation('/stock', new URLSearchParams('lens=cover'))).toBe('cover');
    expect(stockLensFromLocation('/stock', new URLSearchParams('lens=movement'))).toBe('movement');
    expect(stockLensFromLocation('/stock', new URLSearchParams('lens=execution'))).toBe('execution');
    expect(stockLensFromLocation('/channel-intelligence', new URLSearchParams())).toBe('sellthrough');
    expect(stockLensFromLocation('/channel-intelligence/workspace', new URLSearchParams())).toBe('sellthrough');
    expect(stockLensFromLocation('/forecasts', new URLSearchParams())).toBe('forecast');
    expect(stockLensFromLocation('/forecasts/workspace', new URLSearchParams())).toBe('forecast');
  });

  it('owns Inventory by pathname even when a legacy lens parameter is present', () => {
    expect(stockLensFromLocation('/inventory', new URLSearchParams())).toBe('cover');
    expect(stockLensFromLocation('/inventory', new URLSearchParams('product=42'))).toBe('cover');
    expect(stockLensFromLocation('/inventory', new URLSearchParams('lens=movement'))).toBe('cover');
    expect(stockLensFromLocation('/inventory/hand-entered', new URLSearchParams())).toBe('cover');
  });
});
