import { describe, expect, it } from 'vitest';

import { formatDsiPlanFileChannelLabel, formatDsiPlanFileRegionLabel } from './dsiPlanFileGeoDisplay';

describe('formatDsiPlanFileRegionLabel', () => {
  it('returns em dash when evidence absent', () => {
    expect(formatDsiPlanFileRegionLabel(null)).toBe('—');
    expect(formatDsiPlanFileRegionLabel({})).toBe('—');
  });
});

describe('formatDsiPlanFileChannelLabel', () => {
  it('returns em dash when evidence absent', () => {
    expect(formatDsiPlanFileChannelLabel(null, null)).toBe('—');
  });

  it('returns plan raw token when present', () => {
    expect(
      formatDsiPlanFileChannelLabel({ source_channel_raw_token: 'Retail' }, null)
    ).toBe('Retail');
  });

  it('falls back to context samples', () => {
    expect(
      formatDsiPlanFileChannelLabel(
        null,
        { source_channel_raw_samples: ['Wholesale', 'Retail'] }
      )
    ).toBe('Wholesale; Retail');
  });
});
