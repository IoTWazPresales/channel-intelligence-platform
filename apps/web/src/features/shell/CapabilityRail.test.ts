import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';

import { RAIL_WIDTH } from '@/features/shell/CapabilityRail';

const here = dirname(fileURLToPath(import.meta.url));
const prod = readFileSync(join(here, 'CapabilityRail.tsx'), 'utf8');
const lab = readFileSync(join(here, '../../design-lab/shell/LabShell.tsx'), 'utf8');

describe('CapabilityRail BACKLOG-181 port', () => {
  it('rail width fits the longest real group heading; LabShell keeps the mock-up 172', () => {
    // Warren 26 Nov: "How about you do what was told and follow the mockup layouts?" The mock-up's 172px was tried
    // first; the real heading "PROMOTIONS & FUNDING" measures 154.2px at the mock-up's own eyebrow type, more than the
    // 144px content box of a 172px rail, so the production rail is widened by the measured minimum (240px) + 4px spare.
    expect(RAIL_WIDTH).toBe(244);
    expect(lab).toContain('export const RAIL_WIDTH = 172');
  });

  it('carries sticky headers, raised groups, mockup accent rails, and no guide rail', () => {
    for (const src of [prod, lab]) {
      expect(src).toContain("position: 'sticky'");
    }
    // Warren 26 Nov: "How about you do what was told and follow the mockup layouts?" The mock-up sidebar is flat
    // (`--elevated`), so the production rail's pinned headings use the elevated colour, not a raised paper band.
    expect(prod).toContain("bgcolor: 'background.elevated'");
    expect(prod).not.toContain("bgcolor: 'background.paper'");
    expect(lab).toContain("bgcolor: 'background.paper'");
    expect(prod).toContain("borderLeft: '2px solid'");
    expect(prod).toContain("textTransform: 'uppercase'");
    expect(prod).toContain("letterSpacing: '1.4px'");
    expect(prod).not.toContain("borderLeft: '1px solid'");
    expect(lab).not.toContain("borderLeft: '1px solid'");
  });
});
