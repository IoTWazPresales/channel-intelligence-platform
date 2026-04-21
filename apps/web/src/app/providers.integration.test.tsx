import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { Providers } from '@/app/providers';

describe('Providers (integration)', () => {
  it('mounts the query client and theme stack without throwing', () => {
    render(
      <Providers>
        <span data-testid="child">mounted</span>
      </Providers>
    );
    expect(screen.getByTestId('child')).toHaveTextContent('mounted');
  });
});
