'use client';

import '@xyflow/react/dist/style.css';

import {
  Alert,
  Box,
  Button,
  Checkbox,
  CircularProgress,
  FormControlLabel,
  Paper,
  Stack,
  TextField,
  Typography,
} from '@mui/material';
import { alpha, useTheme } from '@mui/material/styles';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  Background,
  Controls,
  Handle,
  MarkerType,
  MiniMap,
  Position,
  ReactFlow,
  useNodes,
  useNodesState,
  useUpdateNodeInternals,
  type NodeProps,
  type ReactFlowInstance,
} from '@xyflow/react';
import { memo, useCallback, useEffect, useMemo, useState } from 'react';

import { AdminChrome } from '@/features/administration/AdminChrome';
import { useCurrentUser, type CurrentUser } from '@/features/shell/useCurrentUser';
import { apiGet, apiPut, safeDisplayError } from '@/lib/api';

import {
  autoLayout,
  COLUMN_LIMIT,
  LAYOUT_URL,
  layoutQueryKey,
  MAP_URL,
  matchesTable,
  NODE_WIDTH,
  relationshipText,
  snapshot,
  type DatabaseForeignKey,
  type DatabaseMapPayload,
  type LayoutDocument,
  type LayoutValue,
  type RelationshipEdge,
  type TableNode,
} from './model';

const DatabaseTableNode = memo(function DatabaseTableNode({
  id,
  data,
  selected,
}: NodeProps<TableNode>) {
  const updateInternals = useUpdateNodeInternals();
  const columns = data.table.columns.filter((column, index) =>
    !data.collapsed || index < COLUMN_LIMIT ||
    (data.query !== '' && column.name.toLowerCase().includes(data.query))
  );

  useEffect(() => {
    updateInternals(id);
  }, [id, data.collapsed, data.query, updateInternals]);

  return (
    <Paper
      variant="outlined"
      sx={{
        width: NODE_WIDTH,
        overflow: 'hidden',
        borderColor: selected || data.matched ? 'primary.main' : 'divider',
        borderWidth: selected || data.matched ? 2 : 1,
        bgcolor: 'background.paper',
        color: 'text.primary',
      }}
    >
      <Handle id="in" type="target" position={Position.Left} isConnectable={false} />
      <Box sx={{ px: 1.5, py: 1, bgcolor: data.matched ? 'action.selected' : 'action.hover' }}>
        <Typography
          variant="subtitle2"
          title={data.table.name}
          sx={{ fontFamily: 'monospace', overflowWrap: 'anywhere' }}
        >
          {data.table.name}
        </Typography>
        <Typography variant="caption" color="text.secondary">
          approx rows: {data.table.approx_rows == null ? 'unknown' : data.table.approx_rows.toLocaleString()}
        </Typography>
      </Box>
      <Box className="nodrag nowheel" sx={{ maxHeight: 480, overflowY: 'auto' }}>
        {columns.map((column) => {
          const matched = data.query !== '' && column.name.toLowerCase().includes(data.query);
          return (
            <Box
              key={column.name}
              title={`${column.name}: ${column.type}; ${column.nullable ? 'nullable' : 'not null'}`}
              sx={{
                display: 'flex',
                alignItems: 'center',
                gap: 0.75,
                minHeight: 26,
                px: 1.5,
                bgcolor: matched ? 'action.selected' : undefined,
                fontFamily: 'monospace',
                fontSize: 12,
              }}
            >
              <Box component="span" sx={{ width: 38, flexShrink: 0, color: 'primary.main' }}>
                {[column.pk ? 'PK' : '', column.fk ? 'FK' : ''].filter(Boolean).join(' ')}
              </Box>
              <Box component="span" sx={{ flex: 1, minWidth: 0, overflowWrap: 'anywhere', fontWeight: matched ? 700 : 400 }}>
                {column.name}
              </Box>
              <Box component="span" sx={{ color: 'text.secondary', maxWidth: 110, overflowWrap: 'anywhere' }}>
                {column.type}{column.nullable ? ' ?' : ''}
              </Box>
            </Box>
          );
        })}
      </Box>
      {data.table.columns.length > COLUMN_LIMIT && (
        <Button
          className="nodrag"
          size="small"
          fullWidth
          aria-expanded={!data.collapsed}
          aria-label={`${data.collapsed ? 'Expand' : 'Collapse'} columns for ${data.table.name}`}
          onClick={() => data.onToggle?.(id)}
        >
          {data.collapsed ? `Show all ${data.table.columns.length} columns` : 'Collapse columns'}
        </Button>
      )}
      <Handle id="out" type="source" position={Position.Right} isConnectable={false} />
    </Paper>
  );
});

const nodeTypes = { table: DatabaseTableNode };

function DatabaseMiniMap() {
  const theme = useTheme();
  const nodes = useNodes<TableNode>();
  // Controlled node props reach ReactFlow's store in an effect. Use that same
  // store as MiniMap so it never renders bounds for an all-hidden node lookup.
  if (!nodes.some((node) => !node.hidden)) return null;
  return (
    <MiniMap
      pannable
      zoomable
      bgColor={theme.palette.background.paper}
      maskColor={alpha(theme.palette.background.default, 0.75)}
      nodeColor={theme.palette.primary.light}
      nodeStrokeColor={theme.palette.divider}
    />
  );
}

function DatabaseDiagram({
  payload,
  initialLayout,
  owner,
  canSave,
}: {
  payload: DatabaseMapPayload;
  initialLayout: LayoutDocument | undefined;
  owner: Pick<CurrentUser, 'id' | 'tenant_id'>;
  canSave: boolean;
}) {
  const theme = useTheme();
  const queryClient = useQueryClient();
  const initialNodes = useMemo(
    () => autoLayout(payload, initialLayout?.value),
    [payload, initialLayout]
  );
  const [nodes, setNodes, onNodesChange] = useNodesState<TableNode>(initialNodes);
  const [savedFingerprint, setSavedFingerprint] = useState(() =>
    initialLayout?.value != null ? JSON.stringify(snapshot(initialNodes)) : ''
  );
  const [search, setSearch] = useState('');
  const [focusNeighbours, setFocusNeighbours] = useState(false);
  const [relationship, setRelationship] = useState<DatabaseForeignKey | null>(null);
  const [flow, setFlow] = useState<ReactFlowInstance<TableNode, RelationshipEdge> | null>(null);
  const [resetGeneration, setResetGeneration] = useState(0);
  const query = search.trim().toLowerCase();

  const toggleColumns = useCallback((id: string) => {
    setNodes((current) => current.map((node) => node.id === id
      ? { ...node, data: { ...node.data, collapsed: !node.data.collapsed } }
      : node));
  }, [setNodes]);

  const matches = useMemo(() => new Set(
    payload.tables.filter((table) => query !== '' && matchesTable(table, query)).map((table) => table.id)
  ), [payload.tables, query]);

  const neighbours = useMemo(() => {
    const result = new Set(matches);
    for (const fk of payload.foreign_keys) {
      if (matches.has(fk.from_table)) result.add(fk.to_table);
      if (matches.has(fk.to_table)) result.add(fk.from_table);
    }
    return result;
  }, [matches, payload.foreign_keys]);

  const displayNodes = useMemo(() => nodes.map((node) => ({
    ...node,
    hidden: query !== '' && focusNeighbours && !neighbours.has(node.id),
    style: {
      opacity: query === '' || matches.has(node.id)
        ? 1
        : focusNeighbours && neighbours.has(node.id) ? 0.75 : 0.2,
    },
    data: { ...node.data, query, matched: matches.has(node.id), onToggle: toggleColumns },
  })), [nodes, query, focusNeighbours, neighbours, matches, toggleColumns]);

  const edges = useMemo<RelationshipEdge[]>(() => payload.foreign_keys.map((fk) => {
    const highlighted = query !== '' && (matches.has(fk.from_table) || matches.has(fk.to_table));
    return {
      id: fk.id,
      source: fk.from_table,
      target: fk.to_table,
      sourceHandle: 'out',
      targetHandle: 'in',
      type: 'smoothstep',
      data: { relationship: fk },
      ariaLabel: relationshipText(fk),
      hidden: query !== '' && focusNeighbours &&
        (!neighbours.has(fk.from_table) || !neighbours.has(fk.to_table)),
      label: highlighted ? `${fk.from_column} → ${fk.to_column}` : undefined,
      labelStyle: { fill: theme.palette.text.primary },
      labelBgStyle: { fill: theme.palette.background.paper },
      markerEnd: {
        type: MarkerType.ArrowClosed,
        color: highlighted ? theme.palette.primary.main : theme.palette.text.secondary,
      },
      style: {
        stroke: highlighted ? theme.palette.primary.main : theme.palette.text.secondary,
        opacity: query === '' || highlighted ? 0.8 : 0.15,
      },
      interactionWidth: 20,
    };
  }), [payload.foreign_keys, query, focusNeighbours, neighbours, matches, theme]);

  useEffect(() => {
    if (!flow || resetGeneration === 0) return;
    const frame = requestAnimationFrame(() => {
      void flow.fitView({ padding: 0.15, duration: 200 });
    });
    return () => cancelAnimationFrame(frame);
  }, [flow, resetGeneration]);

  const value = useMemo(() => snapshot(nodes), [nodes]);
  const dirty = JSON.stringify(value) !== savedFingerprint;
  const save = useMutation({
    mutationFn: (next: LayoutValue) => apiPut<LayoutDocument>(LAYOUT_URL, { value: next }),
    onSuccess: (document, submitted) => {
      setSavedFingerprint(JSON.stringify(submitted));
      queryClient.setQueryData(layoutQueryKey(owner.tenant_id, owner.id), document);
    },
  });

  return (
    <Stack spacing={1.5}>
      <Stack direction={{ xs: 'column', md: 'row' }} spacing={1} alignItems={{ md: 'center' }}>
        <TextField
          size="small"
          label="Search tables or columns"
          value={search}
          onChange={(event) => setSearch(event.target.value)}
          sx={{ minWidth: 250 }}
        />
        <FormControlLabel
          control={<Checkbox checked={focusNeighbours} onChange={(_, checked) => setFocusNeighbours(checked)} />}
          label="Focus on neighbours"
        />
        <Button
          disabled={!flow || (query !== '' && matches.size === 0)}
          onClick={() => {
            const ids = query === '' ? nodes.map((node) => node.id) : [...matches];
            void flow?.fitView({ nodes: ids.map((id) => ({ id })), padding: 0.2, maxZoom: 1, duration: 200 });
          }}
        >
          {query ? 'Fit matches' : 'Fit all'}
        </Button>
        <Button
          onClick={() => {
            setNodes(autoLayout(payload));
            setResetGeneration((current) => current + 1);
          }}
        >
          Reset layout
        </Button>
        <Button
          variant="contained"
          disabled={!canSave || !dirty || save.isPending}
          onClick={() => save.mutate(value)}
        >
          {save.isPending ? 'Saving layout…' : 'Save layout'}
        </Button>
      </Stack>
      <Typography variant="body2" color="text.secondary" role="status">
        {payload.tables.length} tables · {payload.foreign_keys.length} foreign-key column links
        {query ? ` · ${matches.size} matching tables` : ''}
        {' · '}{dirty ? 'Unsaved layout' : 'Layout saved'}
      </Typography>
      <Typography variant="caption" color="text.secondary">
        Public schema only. Approx rows are PostgreSQL estimates; unknown means no estimate.
        PK = primary key, FK = foreign key, ? = nullable. Drag tables, then save your personal layout.
        Search matches names literally; focus keeps matches and their direct neighbours. Click a relationship for its columns.
      </Typography>
      {save.isError && <Alert severity="error">Layout was not saved: {safeDisplayError(save.error)}</Alert>}
      {query !== '' && matches.size === 0 && <Alert severity="info">No table or column matches.</Alert>}
      {relationship && (
        <Alert severity="info" onClose={() => setRelationship(null)}>
          {relationshipText(relationship)}
        </Alert>
      )}
      <Box
          sx={{
            height: { xs: '65vh', md: '72vh' },
            minHeight: 420,
            border: 1,
            borderColor: 'divider',
            borderRadius: 1,
            overflow: 'hidden',
            bgcolor: 'background.default',
            '& .react-flow__controls-button': {
              bgcolor: 'background.paper',
              color: 'text.primary',
              borderColor: 'divider',
              '& svg': { fill: 'currentColor' },
              '&:hover': { bgcolor: 'action.hover' },
            },
          }}
      >
        <ReactFlow<TableNode, RelationshipEdge>
          nodes={displayNodes}
          edges={edges}
          nodeTypes={nodeTypes}
          onNodesChange={onNodesChange}
          onInit={setFlow}
          onEdgeClick={(_, edge) => setRelationship(edge.data?.relationship ?? null)}
          onlyRenderVisibleElements
          nodesConnectable={false}
          edgesReconnectable={false}
          deleteKeyCode={null}
          minZoom={0.02}
          maxZoom={2}
          fitView
          fitViewOptions={{ padding: 0.15 }}
          colorMode={theme.palette.mode}
        >
          <Background color={theme.palette.divider} />
          <DatabaseMiniMap />
          <Controls showInteractive={false} />
        </ReactFlow>
      </Box>
    </Stack>
  );
}

function OwnedDatabaseMap({ owner }: { owner: CurrentUser }) {
  const metadata = useQuery({
    queryKey: ['admin', 'db-map', owner.tenant_id ?? null, owner.id],
    queryFn: ({ signal }) => apiGet<DatabaseMapPayload>(MAP_URL, { signal }),
    staleTime: 60_000,
    refetchOnWindowFocus: false,
    retry: false,
  });
  const layout = useQuery({
    queryKey: layoutQueryKey(owner.tenant_id, owner.id),
    queryFn: ({ signal }) => apiGet<LayoutDocument>(LAYOUT_URL, { signal }),
    staleTime: Infinity,
    refetchOnWindowFocus: false,
    retry: false,
  });

  if (metadata.isPending || layout.isPending || metadata.isFetching || layout.isFetching) {
    return <CircularProgress size={24} aria-label="Loading database map" />;
  }
  if (metadata.isError) {
    return (
      <Alert severity="error" action={<Button onClick={() => void metadata.refetch()}>Retry</Button>}>
        Database map unavailable: {safeDisplayError(metadata.error)}
      </Alert>
    );
  }
  if (metadata.data.tables.length === 0) {
    return <Alert severity="info">No public tables are available.</Alert>;
  }
  return (
    <Stack spacing={1.5}>
      {layout.isError && (
        <Alert severity="warning" action={<Button onClick={() => void layout.refetch()}>Retry layout</Button>}>
          Personal layout could not be restored. Saving is disabled until it can be loaded.
        </Alert>
      )}
      <DatabaseDiagram
        key={layout.isSuccess ? 'restored' : 'unavailable'}
        payload={metadata.data}
        initialLayout={layout.data}
        owner={owner}
        canSave={layout.isSuccess}
      />
    </Stack>
  );
}

export function DatabaseMapPage() {
  const { data: me, isError } = useCurrentUser();
  if (isError || (me && String(me.role).toLowerCase() !== 'admin')) {
    return (
      <AdminChrome>
        <Alert severity="warning">Admin role required to view the database map.</Alert>
      </AdminChrome>
    );
  }
  return (
    <AdminChrome>
      <Typography variant="h6" sx={{ mb: 1.5 }}>Database map</Typography>
      {me
        ? <OwnedDatabaseMap key={JSON.stringify([me.tenant_id, me.id])} owner={me} />
        : <CircularProgress size={24} aria-label="Checking database map access" />}
    </AdminChrome>
  );
}
