import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';

import { RAIL_WIDTH } from '@/features/shell/CapabilityRail';

const here = dirname(fileURLToPath(import.meta.url));
const prod = readFileSync(join(here, 'CapabilityRail.tsx'), 'utf8');
const lab = readFileSync(join(here, '../../design-lab/shell/LabShell.tsx'), 'utf8');

describe('CapabilityRail BACKLOG-181 port', () => {
  it('rail width matches LabShell', () => {
    expect(RAIL_WIDTH).toBe(172);
    expect(lab).toContain('export const RAIL_WIDTH = 172');
  });

  it('carries sticky headers, raised groups, mockup accent rails, and no guide rail', () => {
    for (const src of [prod, lab]) {
      expect(src).toContain("position: 'sticky'");
      expect(src).toContain("bgcolor: 'background.paper'");
    }
    expect(prod).toContain("borderLeft: '2px solid'");
    expect(prod).toContain("textTransform: 'uppercase'");
    expect(prod).toContain("letterSpacing: '1.4px'");
    expect(prod).not.toContain("borderLeft: '1px solid'");
    expect(lab).not.toContain("borderLeft: '1px solid'");
  });
});
