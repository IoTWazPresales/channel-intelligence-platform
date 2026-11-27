import { describe, expect, it } from 'vitest';

import { renderWithProviders } from '@/test-utils/renderWithProviders';

import { Panel } from './Panel';

describe('Panel', () => {
  it('uses the theme panel title and the shared shadow token', () => {
    const { getByText } = renderWithProviders(<Panel title="Stock cover">body</Panel>);
    const title = getByText('Stock cover');
    expect(title.tagName).toBe('H2');
    expect(getComputedStyle(title).fontWeight).toBe('650');
    expect(getComputedStyle(title).fontSize).toBe('0.875rem');
    const paper = title.closest('.MuiPaper-root');
    expect(paper).not.toBeNull();
    expect(getComputedStyle(paper as Element).boxShadow).not.toBe('none');
  });
});
