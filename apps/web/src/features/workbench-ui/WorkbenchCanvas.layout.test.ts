import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';

const src = readFileSync(join(dirname(fileURLToPath(import.meta.url)), 'WorkbenchCanvas.tsx'), 'utf8');

describe('WorkbenchCanvas layout (dashboard-v2 main inset)', () => {
  it('uses mockup-aligned desktop padding (22px horizontal, 18px top)', () => {
    expect(src).toContain('md: 2.75');
    expect(src).toContain('md: 2.25');
  });
});