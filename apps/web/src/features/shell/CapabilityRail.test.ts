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
    expect(RAIL_WIDTH).toBe(252);
    expect(lab).toContain('export const RAIL_WIDTH = 252');
  });

  it('carries the lab leaf marker, sticky header, raised group, and no guide rail', () => {
    for (const src of [prod, lab]) {
      expect(src).toContain("position: 'sticky'");
      expect(src).toContain("width: '3px'");
      expect(src).toContain("height: '15px'");
      expect(src).toContain("borderRadius: '2px'");
      expect(src).toContain("bgcolor: 'background.paper'");
      expect(src).toContain("'&.Mui-selected': { bgcolor: 'transparent' }");
    }
    expect(prod).not.toContain("borderLeft: '1px solid'");
    expect(lab).not.toContain("borderLeft: '1px solid'");
  });
});
