import { render, type RenderOptions } from '@testing-library/react';
import type { ReactElement, ReactNode } from 'react';

import { CipThemeProvider } from '@/theme/CipThemeProvider';

function Wrapper({ children }: { children: ReactNode }) {
  return <CipThemeProvider>{children}</CipThemeProvider>;
}

export function renderWithProviders(ui: ReactElement, options?: Omit<RenderOptions, 'wrapper'>) {
  return render(ui, { wrapper: Wrapper, ...options });
}
