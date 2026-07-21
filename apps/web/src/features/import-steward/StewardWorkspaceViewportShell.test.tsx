import { describe, expect, it } from 'vitest';
import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { StewardWorkspaceViewportShell } from './StewardWorkspaceViewportShell';

describe('StewardWorkspaceViewportShell', () => {
  it('applies viewport-capped left column styles (md)', () => {
    const html = renderToStaticMarkup(
      createElement(StewardWorkspaceViewportShell, {
        rootTestId: 'shell',
        left: createElement('div', { 'data-left': true }, 'left'),
        drawer: createElement('aside', { 'data-drawer': true }, 'drawer'),
      }),
    );
    expect(html).toContain('data-testid="shell"');
    expect(html).toContain('data-testid="shell-left"');
    expect(html).toContain('data-left');
    expect(html).toContain('data-drawer');
  });

  it('supports bordered chrome without dropping the left slot', () => {
    const html = renderToStaticMarkup(
      createElement(StewardWorkspaceViewportShell, {
        bordered: true,
        left: createElement('span', null, 'L'),
      }),
    );
    expect(html).toContain('>L<');
  });
});
