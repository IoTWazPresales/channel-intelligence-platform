import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';

const src = readFileSync(join(dirname(fileURLToPath(import.meta.url)), 'AppShell.tsx'), 'utf8');

describe('AppShell scroll', () => {
  it('keeps the top bar in the column and scrolls the page body', () => {
    const header = src.slice(src.indexOf('data-testid="app-topbar"'), src.indexOf('data-testid="topbar-context"'));
    expect(header).not.toContain("position: 'sticky'");
    expect(src).toContain("overflow: 'auto'");
    expect(src).toContain("height: '100vh'");
    expect(src).toContain("overflow: 'hidden'");
  });
});
