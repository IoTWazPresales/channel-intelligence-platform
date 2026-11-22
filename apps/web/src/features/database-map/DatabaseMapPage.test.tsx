import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import type { ReactNode } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import Page from '@/app/(app)/admin/db-map/page';
import { AUTH_ME_QUERY_KEY, type CurrentUser } from '@/features/shell/useCurrentUser';
import { apiGet, apiPut } from '@/lib/api';

import {
  autoLayout,
  LAYOUT_KEY,
  LAYOUT_URL,
  MAP_URL,
  type DatabaseMapPayload,
  type LayoutDocument,
  type LayoutValue,
  type TableNode,
} from './model';

const { fitView } = vi.hoisted(() => ({ fitView: vi.fn().mockResolvedValue(true) }));

vi.mock('@/lib/api', () => ({
  apiGet: vi.fn(),
  apiPut: vi.fn(),
  safeDisplayError: (error: unknown) => error instanceof Error ? error.message : String(error),
}));

vi.mock('@/features/administration/AdminChrome', () => ({
  AdminChrome: ({ children }: { children: ReactNode }) => children,
}));

vi.mock('@xyflow/react', async () => {
  const actual = await vi.importActual<typeof import('@xyflow/react')>('@xyflow/react');
  const React = await import('react');
  const instance = { fitView };
  const updateInternals = vi.fn();

  function MockFlow({
    nodes,
    edges,
    nodeTypes,
    onNodesChange,
    onInit,
    children,
    onlyRenderVisibleElements,
    nodesConnectable,
    edgesReconnectable,
    deleteKeyCode,
  }: {
    nodes: TableNode[];
    edges: import('./model').RelationshipEdge[];
    nodeTypes: Record<string, React.ComponentType<import('@xyflow/react').NodeProps<TableNode>>>;
    onNodesChange: (changes: import('@xyflow/react').NodeChange<TableNode>[]) => void;
    onInit: (instance: import('@xyflow/react').ReactFlowInstance) => void;
    children: ReactNode;
    onlyRenderVisibleElements: boolean;
    nodesConnectable: boolean;
    edgesReconnectable: boolean;
    deleteKeyCode: unknown;
  }) {
    React.useEffect(() => {
      onInit(instance as unknown as import('@xyflow/react').ReactFlowInstance);
    }, [onInit]);
    return (
      <div
        data-testid="flow"
        data-virtualized={String(onlyRenderVisibleElements)}
        data-connectable={String(nodesConnectable)}
        data-reconnectable={String(edgesReconnectable)}
        data-delete-key={String(deleteKeyCode)}
      >
        {nodes.filter((node) => !node.hidden).map((node) => {
          const Component = nodeTypes.table;
          return (
            <div
              key={node.id}
              data-testid={`node-${node.id}`}
              data-x={node.position.x}
              data-y={node.position.y}
              style={node.style}
            >
              <Component
                id={node.id}
                type="table"
                data={node.data}
                dragging={false}
                selected={false}
                zIndex={0}
                isConnectable={false}
                draggable
                selectable
                deletable={false}
                positionAbsoluteX={node.position.x}
                positionAbsoluteY={node.position.y}
              />
              <button onClick={() => onNodesChange([{
                id: node.id,
                type: 'position',
                position: { x: 123, y: 456 },
              }])}>
                Drag {node.data.table.name}
              </button>
            </div>
          );
        })}
        {edges.filter((edge) => !edge.hidden).map((edge) => (
          <div key={edge.id} data-testid={`edge-${edge.id}`}>
            {edge.source} → {edge.target}
          </div>
        ))}
        {children}
      </div>
    );
  }

  return {
    ...actual,
    ReactFlow: MockFlow,
    Handle: () => null,
    Controls: () => <div data-testid="zoom-controls" />,
    MiniMap: () => <div data-testid="minimap" />,
    Background: () => null,
    useUpdateNodeInternals: () => updateInternals,
  };
});

const column = (name: string, pk = false, fk = false) => ({
  name, type: 'bigint', nullable: !pk, pk, fk,
});

const payload: DatabaseMapPayload = {
  schema_name: 'public',
  row_count_kind: 'approx rows',
  generated_at: '2026-11-20T08:00:00Z',
  tables: [
    { id: 'public.parent', name: 'parent', approx_rows: 100, columns: [column('id', true)] },
    {
      id: 'public.child',
      name: 'child',
      approx_rows: null,
      columns: [
        column('id', true),
        column('parent_id', false, true),
        ...Array.from({ length: 7 }, (_, index) => column(`detail_${index}`)),
        column('hidden_reference'),
      ],
    },
    { id: 'public.island', name: 'island', approx_rows: 0, columns: [column('id', true)] },
  ],
  foreign_keys: [{
    id: 'fk-child',
    name: 'child_parent_fk',
    from_table: 'public.child',
    from_column: 'parent_id',
    to_table: 'public.parent',
    to_column: 'id',
    ordinal: 1,
  }],
};

let me: CurrentUser;
let layout: LayoutDocument;

function mount(client = new QueryClient({
  defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
})) {
  render(<QueryClientProvider client={client}><Page /></QueryClientProvider>);
  return client;
}

beforeEach(() => {
  vi.clearAllMocks();
  me = { id: '101', tenant_id: 'tenant-a', role: 'admin' };
  layout = { key: LAYOUT_KEY, value: null, updated_at: null };
  vi.mocked(apiGet).mockImplementation(async (path) => {
    if (path === '/api/v1/auth/me') return me;
    if (path === MAP_URL) return payload;
    if (path === LAYOUT_URL) return layout;
    throw new Error(`Unexpected GET ${path}`);
  });
  vi.mocked(apiPut).mockImplementation(async (_path, body) => ({
    key: LAYOUT_KEY,
    value: (body as { value: LayoutValue }).value,
    updated_at: '2026-11-20T09:00:00Z',
  }));
});

describe('admin database map', () => {
  it('renders schema nodes and relationships with virtualisation and read-only graph controls', async () => {
    mount();
    await screen.findByTestId('node-public.child');
    expect(screen.getByTestId('node-public.parent')).toBeInTheDocument();
    expect(screen.getByTestId('edge-fk-child')).toHaveTextContent('public.child → public.parent');
    expect(screen.getByText('approx rows: unknown')).toBeInTheDocument();
    const child = within(screen.getByTestId('node-public.child'));
    expect(child.getByText('PK')).toBeInTheDocument();
    expect(child.getByText('FK')).toBeInTheDocument();
    expect(child.queryByText('hidden_reference')).not.toBeInTheDocument();
    expect(screen.getByTestId('flow')).toHaveAttribute('data-virtualized', 'true');
    expect(screen.getByTestId('flow')).toHaveAttribute('data-connectable', 'false');
    expect(screen.getByTestId('flow')).toHaveAttribute('data-reconnectable', 'false');
    expect(screen.getByTestId('flow')).toHaveAttribute('data-delete-key', 'null');
    expect(screen.getByTestId('minimap')).toBeInTheDocument();
    expect(screen.getByTestId('zoom-controls')).toBeInTheDocument();
    expect(apiPut).not.toHaveBeenCalled();
  });

  it('finds hidden column names, dims other tables and focuses direct neighbours', async () => {
    mount();
    await screen.findByTestId('node-public.child');
    fireEvent.change(screen.getByLabelText('Search tables or columns'), {
      target: { value: 'hidden_reference' },
    });
    expect(screen.getByText('hidden_reference')).toBeInTheDocument();
    expect(screen.getByTestId('node-public.island')).toHaveStyle({ opacity: '0.2' });
    expect(screen.getByRole('status')).toHaveTextContent('1 matching tables');
    fireEvent.click(screen.getByLabelText('Focus on neighbours'));
    expect(screen.getByTestId('node-public.child')).toBeInTheDocument();
    expect(screen.getByTestId('node-public.parent')).toBeInTheDocument();
    expect(screen.queryByTestId('node-public.island')).not.toBeInTheDocument();
    expect(screen.getByTestId('edge-fk-child')).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText('Search tables or columns'), {
      target: { value: 'no_such_column' },
    });
    expect(screen.getByText('No table or column matches.')).toBeInTheDocument();
    expect(screen.queryByTestId('node-public.child')).not.toBeInTheDocument();
    fireEvent.change(screen.getByLabelText('Search tables or columns'), {
      target: { value: '' },
    });
    expect(screen.getByTestId('node-public.island')).toBeInTheDocument();
  });

  it.each([false, true])('fits only search matches without changing saved positions (neighbour focus: %s)', async (focusNeighbours) => {
    const savedNodes = {
      'public.parent': { x: 90000, y: 80000, collapsed: false },
      'public.child': { x: 11, y: 22, collapsed: true },
      'public.island': { x: 300, y: 400, collapsed: false },
    };
    layout.value = { version: 1, nodes: savedNodes };
    mount();
    await screen.findByTestId('node-public.child');
    fireEvent.change(screen.getByLabelText('Search tables or columns'), {
      target: { value: 'hidden_reference' },
    });
    if (focusNeighbours) fireEvent.click(screen.getByLabelText('Focus on neighbours'));
    expect(screen.getByTestId('node-public.parent')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Fit matches' }));
    expect(fitView).toHaveBeenCalledTimes(1);
    expect(fitView).toHaveBeenLastCalledWith({
      nodes: [{ id: 'public.child' }], padding: 0.2, maxZoom: 1, duration: 200,
    });

    fireEvent.change(screen.getByLabelText('Search tables or columns'), {
      target: { value: '' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Fit all' }));
    expect(fitView).toHaveBeenLastCalledWith({
      nodes: payload.tables.map(({ id }) => ({ id })), padding: 0.2, maxZoom: 1, duration: 200,
    });
    for (const [id, position] of Object.entries(savedNodes)) {
      const node = screen.getByTestId(`node-${id}`);
      expect(node).toHaveAttribute('data-x', String(position.x));
      expect(node).toHaveAttribute('data-y', String(position.y));
    }
    expect(screen.getByRole('button', { name: 'Expand columns for child' })).toBeInTheDocument();
    expect(screen.getByRole('status')).toHaveTextContent('Layout saved');
    expect(screen.getByRole('button', { name: 'Save layout' })).toBeDisabled();
    expect(apiPut).not.toHaveBeenCalled();
  });

  it('omits the minimap only while neighbour focus hides every node and restores it on clear', async () => {
    mount();
    await screen.findByTestId('node-public.child');
    const search = screen.getByLabelText('Search tables or columns');
    const focus = screen.getByLabelText('Focus on neighbours');
    fireEvent.change(search, { target: { value: 'no_such_column' } });
    expect(screen.getByText('No table or column matches.')).toBeInTheDocument();
    expect(screen.getByTestId('minimap')).toBeInTheDocument();
    fireEvent.click(focus);
    expect(screen.queryByTestId('node-public.child')).not.toBeInTheDocument();
    expect(screen.queryByTestId('node-public.parent')).not.toBeInTheDocument();
    expect(screen.queryByTestId('node-public.island')).not.toBeInTheDocument();
    expect(screen.queryByTestId('minimap')).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Fit matches' })).toBeDisabled();
    fireEvent.click(focus);
    expect(screen.getByTestId('minimap')).toBeInTheDocument();
    fireEvent.click(focus);
    expect(screen.queryByTestId('minimap')).not.toBeInTheDocument();
    fireEvent.change(search, { target: { value: '' } });
    expect(screen.getByTestId('node-public.child')).toBeInTheDocument();
    expect(screen.getByTestId('node-public.parent')).toBeInTheDocument();
    expect(screen.getByTestId('node-public.island')).toBeInTheDocument();
    expect(screen.getByTestId('minimap')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Fit all' })).toBeEnabled();
    expect(fitView).not.toHaveBeenCalled();
    expect(apiPut).not.toHaveBeenCalled();
  });

  it('restores positions and expanded columns, then saves only layout data after dragging', async () => {
    layout.value = {
      version: 1,
      nodes: { 'public.child': { x: 11, y: 22, collapsed: false } },
    };
    mount();
    const child = await screen.findByTestId('node-public.child');
    expect(child).toHaveAttribute('data-x', '11');
    expect(child).toHaveAttribute('data-y', '22');
    expect(within(child).getByText('hidden_reference')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Save layout' })).toBeDisabled();
    expect(apiGet).toHaveBeenCalledWith(LAYOUT_URL, expect.objectContaining({ signal: expect.anything() }));

    fireEvent.click(screen.getByRole('button', { name: 'Collapse columns for child' }));
    fireEvent.click(screen.getByRole('button', { name: 'Drag child' }));
    fireEvent.click(screen.getByRole('button', { name: 'Save layout' }));
    await waitFor(() => expect(apiPut).toHaveBeenCalledWith(LAYOUT_URL, {
      value: expect.objectContaining({
        version: 1,
        nodes: expect.objectContaining({
          'public.child': { x: 123, y: 456, collapsed: true },
        }),
      }),
    }));
    await waitFor(() => expect(screen.getByRole('status')).toHaveTextContent('Layout saved'));
    const body = vi.mocked(apiPut).mock.calls[0][1] as { value: LayoutValue };
    expect(Object.keys(body)).toEqual(['value']);
    expect(Object.keys(body.value.nodes['public.child']).sort()).toEqual(['collapsed', 'x', 'y']);
  });

  it('resets to automatic positions and collapsed defaults without writing until Save', async () => {
    layout.value = {
      version: 1,
      nodes: { 'public.child': { x: 90000, y: 80000, collapsed: false } },
    };
    mount();
    await screen.findByTestId('node-public.child');
    fireEvent.click(screen.getByRole('button', { name: 'Reset layout' }));
    expect(screen.getByTestId('node-public.child')).not.toHaveAttribute('data-x', '90000');
    expect(screen.getByRole('button', { name: 'Expand columns for child' })).toBeInTheDocument();
    expect(apiPut).not.toHaveBeenCalled();
    expect(screen.getByRole('button', { name: 'Save layout' })).toBeEnabled();
  });

  it('does not load metadata or layouts for a non-admin', async () => {
    me.role = 'planner';
    mount();
    await screen.findByText('Admin role required to view the database map.');
    expect(apiGet).toHaveBeenCalledTimes(1);
    expect(apiGet).toHaveBeenCalledWith('/api/v1/auth/me');
    expect(apiPut).not.toHaveBeenCalled();
  });

  it('uses another account’s layout on a retained QueryClient', async () => {
    layout.value = {
      version: 1,
      nodes: { 'public.child': { x: 11, y: 22, collapsed: true } },
    };
    const client = mount();
    expect(await screen.findByTestId('node-public.child')).toHaveAttribute('data-x', '11');
    layout = {
      key: LAYOUT_KEY,
      value: { version: 1, nodes: { 'public.child': { x: 77, y: 88, collapsed: false } } },
      updated_at: null,
    };
    client.setQueryData(AUTH_ME_QUERY_KEY, { ...me, id: '202', tenant_id: 'tenant-b' });
    await waitFor(() => expect(screen.getByTestId('node-public.child')).toHaveAttribute('data-x', '77'));
    expect(vi.mocked(apiGet).mock.calls.filter(([path]) => path === LAYOUT_URL)).toHaveLength(2);
  });

  it('keeps the map usable and refuses to overwrite an unreadable saved layout', async () => {
    vi.mocked(apiGet).mockImplementation(async (path) => {
      if (path === '/api/v1/auth/me') return me;
      if (path === MAP_URL) return payload;
      throw new Error('layout unavailable');
    });
    mount();
    await screen.findByTestId('node-public.child');
    expect(screen.getByText(/Personal layout could not be restored/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Drag child' }));
    expect(screen.getByRole('button', { name: 'Save layout' })).toBeDisabled();
    expect(apiPut).not.toHaveBeenCalled();
  });

  it('ignores invalid or removed saved nodes and lays out newly discovered tables', () => {
    const nodes = autoLayout(payload, {
      version: 1,
      nodes: {
        'public.child': { x: Number.NaN, y: 5, collapsed: true },
        'public.removed': { x: 1, y: 2, collapsed: true },
      },
    });
    expect(nodes).toHaveLength(payload.tables.length);
    expect(nodes.some((node) => node.id === 'public.removed')).toBe(false);
    expect(nodes.every((node) =>
      Number.isFinite(node.position.x) && Number.isFinite(node.position.y)
    )).toBe(true);
  });
});
