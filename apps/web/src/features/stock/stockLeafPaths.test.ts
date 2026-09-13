import { describe, expect, it } from 'vitest';

import {
  FORECAST_HREF,
  FORECAST_WORKSPACE_HREF,
  SELLTHROUGH_HREF,
  SELLTHROUGH_WORKSPACE_HREF,
} from './stockLeafPaths';

describe('stock leftover leaf paths', () => {
  it('keeps rail landings and relocates workspaces under them', () => {
    expect(SELLTHROUGH_HREF).toBe('/channel-intelligence');
    expect(SELLTHROUGH_WORKSPACE_HREF).toBe('/channel-intelligence/workspace');
    expect(FORECAST_HREF).toBe('/forecasts');
    expect(FORECAST_WORKSPACE_HREF).toBe('/forecasts/workspace');
  });
});
