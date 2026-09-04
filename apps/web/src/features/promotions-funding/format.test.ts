import { describe, expect, it } from 'vitest';

import { fmtCompact } from './format';

describe('fmtCompact (I1 display grain)', () => {
  it('rounds line-sum 368640 to R369k and the stale list figure 486400 to R486k', () => {
    expect(fmtCompact(368_640)).toBe('R369k');
    expect(fmtCompact(486_400)).toBe('R486k');
    expect(fmtCompact(368_640)).not.toBe(fmtCompact(486_400));
  });
});
