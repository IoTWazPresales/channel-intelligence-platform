import { describe, expect, it } from 'vitest';

import {
  chunkDsiBulkCandidateIds,
  mergeDsiBulkPreviewResponses,
} from './dsiBulkStewardChunking';

describe('dsiBulkStewardChunking', () => {
  it('chunks ids above ignore cap', () => {
    const ids = Array.from({ length: 505 }, (_, i) => i + 1);
    const chunks = chunkDsiBulkCandidateIds(ids, 1000);
    expect(chunks).toHaveLength(1);
    expect(chunks[0]).toHaveLength(505);
  });

  it('splits when above chunk size', () => {
    const ids = Array.from({ length: 250 }, (_, i) => i + 1);
    const chunks = chunkDsiBulkCandidateIds(ids, 200);
    expect(chunks).toHaveLength(2);
    expect(chunks[0]).toHaveLength(200);
    expect(chunks[1]).toHaveLength(50);
  });

  it('merges preview totals across chunks', () => {
    const merged = mergeDsiBulkPreviewResponses(96, 'ignore', [
      {
        import_job_id: 96,
        action: 'ignore',
        results: [{ candidate_id: 1, ok: true }],
        totals: { ok_count: 1, not_ok_count: 0, staging_rows_affected: 10 },
      },
      {
        import_job_id: 96,
        action: 'ignore',
        results: [{ candidate_id: 2, ok: true }],
        totals: { ok_count: 1, not_ok_count: 0, staging_rows_affected: 5 },
      },
    ]);
    expect(merged.results).toHaveLength(2);
    expect(merged.totals.ok_count).toBe(2);
    expect(merged.totals.staging_rows_affected).toBe(15);
  });
});
