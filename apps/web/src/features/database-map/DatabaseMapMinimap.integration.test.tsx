import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen } from '@testing-library/react';
import type { ReactNode } from 'react';
import { expect, it, vi } from 'vitest';

import { DatabaseMapPage } from './DatabaseMapPage';
import { LAYOUT_KEY, LAYOUT_URL, MAP_URL, type TableNode } from './model';

const { invalidSvg } = vi.hoisted(() => ({ invalidSvg: [] as string[] }));

vi.mock('@/features/administration/AdminChrome', () => ({
  AdminChrome: ({ children }: { children: ReactNode }) => children,
}));
vi.mock('@/lib/api', () => ({
  apiGet: vi.fn(async (path: string) => {
    if (path === '/api/v1/auth/me') return { id: '101', tenant_id: 'default', role: 'admin' };
    if (path === LAYOUT_URL) return { key: LAYOUT_KEY, value: null, updated_at: null };
    if (path === MAP_URL) return {
      schema_name: 'public', row_count_kind: 'approx rows', generated_at: '',
      tables: [{ id: 'public.example', name: 'example', approx_rows: 1, columns: [
        { name: 'id', type: 'bigint', nullable: false, pk: true, fk: false },
      ] }], foreign_keys: [],
    };
    throw new Error(`Unexpected request: ${path}`);
  }),
  apiPut: vi.fn(),
  safeDisplayError: String,
}));

vi.mock('@xyflow/react', async () => {
  const actual = await vi.importActual<typeof import('@xyflow/react')>('@xyflow/react');
  const React = await import('react');
  const instance = { fitView: vi.fn().mockResolvedValue(true) };

  function ControlledNodes({ nodes, children }: { nodes: TableNode[]; children: ReactNode }) {
    const store = actual.useStoreApi();
    // ReactFlow's StoreUpdater also copies controlled props in a passive effect.
    React.useEffect(() => { store.getState().setNodes(nodes); }, [nodes, store]);
    React.useLayoutEffect(() => {
      // Inspect the intermediate commit before that effect updates the store.
      for (const element of document.querySelectorAll('.react-flow__minimap svg, .react-flow__minimap svg *')) {
        for (const attribute of element.attributes) {
          if (/NaN|Infinity/.test(attribute.value)) invalidSvg.push(`${attribute.name}=${attribute.value}`);
        }
      }
    });
    return children;
  }

  function ControlledFlow({ nodes, children, onInit }: {
    nodes: TableNode[]; children: ReactNode;
    onInit: (flow: import('@xyflow/react').ReactFlowInstance) => void;
  }) {
    React.useEffect(() => { onInit(instance as unknown as import('@xyflow/react').ReactFlowInstance); }, [onInit]);
    return (
      <actual.ReactFlowProvider initialNodes={nodes} initialWidth={1000} initialHeight={600}>
        <ControlledNodes nodes={nodes}>{children}</ControlledNodes>
      </actual.ReactFlowProvider>
    );
  }
  // Keep the real provider, store, useNodes and MiniMap/SVG renderer. Omit the
  // canvas and pan/zoom machinery that need browser geometry, covered in smoke.
  return { ...actual, ReactFlow: ControlledFlow, Background: () => null, Controls: () => null };
});

it('keeps real minimap SVG finite throughout focused empty-to-visible store transitions', async () => {
  const { apiPut } = await import('@/lib/api');
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const { container } = render(<QueryClientProvider client={client}><DatabaseMapPage /></QueryClientProvider>);
  const search = await screen.findByRole('textbox', { name: 'Search tables or columns' });
  const focus = screen.getByRole('checkbox', { name: 'Focus on neighbours' });
  expect(container.querySelector('.react-flow__minimap')).not.toBeNull();
  fireEvent.click(focus);
  for (let cycle = 0; cycle < 3; cycle += 1) {
    fireEvent.change(search, { target: { value: 'no_such_table' } });
    expect(container.querySelector('.react-flow__minimap')).toBeNull();
    fireEvent.change(search, { target: { value: '' } });
    expect(container.querySelector('.react-flow__minimap')).not.toBeNull();
  }
  fireEvent.change(search, { target: { value: 'no_such_table' } });
  fireEvent.click(focus);
  expect(container.querySelector('.react-flow__minimap')).not.toBeNull();
  expect(invalidSvg).toEqual([]);
  expect(apiPut).not.toHaveBeenCalled();
});
