import { describe, expect, it } from 'vitest';

import { stockLensFromLocation } from './StockChrome';

describe('stockLensFromLocation', () => {
  it('maps production routes onto the lab stock lenses', () => {
    expect(stockLensFromLocation('/stock', new URLSearchParams())).toBe('cover');
    expect(stockLensFromLocation('/stock', new URLSearchParams('lens=cover'))).toBe('cover');
    expect(stockLensFromLocation('/stock', new URLSearchParams('lens=movement'))).toBe('movement');
    expect(stockLensFromLocation('/stock', new URLSearchParams('lens=execution'))).toBe('execution');
    expect(stockLensFromLocation('/channel-intelligence', new URLSearchParams())).toBe('sellthrough');
    expect(stockLensFromLocation('/forecasts', new URLSearchParams())).toBe('forecast');
  });
});
