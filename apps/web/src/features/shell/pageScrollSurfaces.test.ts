import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';

const root = join(dirname(fileURLToPath(import.meta.url)), '..', '..');

function read(rel: string) {
  return readFileSync(join(root, rel), 'utf8');
}

/** Page roots must not stretch to the viewport inside the shell scroller (creates empty scroll). */
const PAGE_SURFACES = [
  'features/brief/BriefPageContent.tsx',
  'features/stock/StockContainer.tsx',
  'features/lineup/LineupContainer.tsx',
  'features/lineup/LineupWorkspace.tsx',
];

describe('page scroll surfaces', () => {
  it.each(PAGE_SURFACES)('%s does not use viewport-stretch flex on the page root', (rel) => {
    const src = read(rel);
    expect(src).not.toMatch(/flex:\s*1,\s*minHeight:\s*0/);
    expect(src).not.toMatch(/flex:\s*1,\s*overflow:\s*['"]auto['"]/);
  });
});