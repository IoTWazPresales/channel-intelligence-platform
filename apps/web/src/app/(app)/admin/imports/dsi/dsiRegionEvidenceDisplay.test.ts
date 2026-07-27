import { describe, expect, it } from 'vitest';

import { formatDsiRegionEvidenceDisplay } from './dsiRegionEvidenceDisplay';
import type { DsiRegionEvidenceDto } from './dsiSteward.types';

describe('formatDsiRegionEvidenceDisplay', () => {
  it('returns null when there is no suggested region', () => {
    const ev: DsiRegionEvidenceDto = {
      suggested_region_id: null,
      confidence: 0,
      explanation_summary: 'No region evidence',
      explanation_factors: [],
      channel_geographic_hints: [],
      province_evidence: {},
    };
    expect(formatDsiRegionEvidenceDisplay(ev)).toBeNull();
  });

  it('labels job fallback distinctly from evidence', () => {
    const ev: DsiRegionEvidenceDto = {
      suggested_region_id: 42,
      confidence: 0.45,
      explanation_summary: 'Suggested region: ZA',
      explanation_factors: [
        {
          source: 'job_fallback',
          detail: 'steward_enabled_operating_region_fallback',
          region_id: 42,
          region_code: 'ZA',
        },
      ],
      channel_geographic_hints: [],
      province_evidence: {},
    };
    expect(formatDsiRegionEvidenceDisplay(ev)).toEqual({
      line: 'Fallback region: ZA',
      sourceLabel: 'Operating region fallback (plan setting)',
      kind: 'fallback',
    });
  });

  it('labels evidence-based suggestion with confidence and source', () => {
    const ev: DsiRegionEvidenceDto = {
      suggested_region_id: 7,
      confidence: 0.72,
      explanation_summary: 'Suggested region: US',
      explanation_factors: [
        {
          source: 'distributor_location',
          detail: 'primary_location_country_code=US',
          region_id: 7,
          region_code: 'US',
        },
      ],
      channel_geographic_hints: [],
      province_evidence: {},
    };
    expect(formatDsiRegionEvidenceDisplay(ev)).toEqual({
      line: 'Suggested region: US (72%)',
      sourceLabel: 'Distributor location',
      kind: 'suggested',
    });
  });

  it('prefers higher-confidence factor when multiple match the same region', () => {
    const ev: DsiRegionEvidenceDto = {
      suggested_region_id: 42,
      confidence: 0.82,
      explanation_summary: 'Suggested region: ZA',
      explanation_factors: [
        {
          source: 'job_fallback',
          region_id: 42,
          region_code: 'ZA',
        },
        {
          source: 'channel_geographic_hint',
          region_id: 42,
          region_code: 'ZA',
        },
      ],
      channel_geographic_hints: [],
      province_evidence: {},
    };
    expect(formatDsiRegionEvidenceDisplay(ev)?.kind).toBe('suggested');
    expect(formatDsiRegionEvidenceDisplay(ev)?.line).toBe('Suggested region: ZA (82%)');
  });
});
