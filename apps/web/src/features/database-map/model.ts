import * as dagre from '@dagrejs/dagre';
import type { Edge, Node } from '@xyflow/react';

export const MAP_URL = '/api/v1/admin/db-map';
export const LAYOUT_KEY = 'admin.db-map.v1';
export const LAYOUT_URL = `/api/v1/me/ui-layout/${LAYOUT_KEY}`;
export const COLUMN_LIMIT = 8;
export const NODE_WIDTH = 340;

export type DatabaseColumn = {
  name: string;
  type: string;
  nullable: boolean;
  pk: boolean;
  fk: boolean;
};

export type DatabaseTable = {
  id: string;
  name: string;
  approx_rows: number | null;
  columns: DatabaseColumn[];
};

export type DatabaseForeignKey = {
  id: string;
  name: string;
  from_table: string;
  from_column: string;
  to_table: string;
  to_column: string;
  ordinal: number;
};

export type DatabaseMapPayload = {
  schema_name: 'public';
  row_count_kind: 'approx rows';
  generated_at: string;
  tables: DatabaseTable[];
  foreign_keys: DatabaseForeignKey[];
};

export type LayoutValue = {
  version: 1;
  nodes: Record<string, { x: number; y: number; collapsed: boolean }>;
};

export type LayoutDocument = {
  key: string;
  value: unknown;
  updated_at: string | null;
};

export type TableNodeData = {
  table: DatabaseTable;
  collapsed: boolean;
  query: string;
  matched: boolean;
  onToggle?: (id: string) => void;
};

export type TableNode = Node<TableNodeData, 'table'>;
export type RelationshipEdge = Edge<{ relationship: DatabaseForeignKey }>;

export function layoutQueryKey(tenantId: string | null | undefined, userId: string) {
  return ['me', 'ui-layout', tenantId ?? null, userId, LAYOUT_KEY] as const;
}

function record(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function storedNode(value: unknown): LayoutValue['nodes'][string] | undefined {
  if (!record(value)) return undefined;
  const { x, y, collapsed } = value;
  if (
    typeof x !== 'number' || !Number.isFinite(x) || Math.abs(x) > 10_000_000 ||
    typeof y !== 'number' || !Number.isFinite(y) || Math.abs(y) > 10_000_000 ||
    typeof collapsed !== 'boolean'
  ) return undefined;
  return { x, y, collapsed };
}

export function autoLayout(payload: DatabaseMapPayload, saved?: unknown): TableNode[] {
  const savedNodes = record(saved) && saved.version === 1 && record(saved.nodes) ? saved.nodes : {};
  const graph = new dagre.graphlib.Graph();
  graph.setGraph({
    rankdir: 'LR',
    ranker: 'longest-path',
    nodesep: 50,
    ranksep: 100,
    marginx: 30,
    marginy: 30,
  });
  graph.setDefaultEdgeLabel(() => ({}));

  const nodes: TableNode[] = payload.tables.map((table) => {
    const stored = storedNode(savedNodes[table.id]);
    const collapsed = stored?.collapsed ?? table.columns.length > COLUMN_LIMIT;
    const visibleCount = collapsed ? Math.min(COLUMN_LIMIT, table.columns.length) : table.columns.length;
    const height = 76 + Math.min(480, visibleCount * 26) + (table.columns.length > COLUMN_LIMIT ? 40 : 0);
    graph.setNode(table.id, { width: NODE_WIDTH, height });
    return {
      id: table.id,
      type: 'table',
      position: { x: 0, y: 0 },
      data: { table, collapsed, query: '', matched: false },
    };
  });
  for (const fk of payload.foreign_keys) {
    if (graph.hasNode(fk.from_table) && graph.hasNode(fk.to_table)) {
      graph.setEdge(fk.from_table, fk.to_table);
    }
  }
  if (nodes.length > 0) dagre.layout(graph);
  return nodes.map((node) => {
    const stored = storedNode(savedNodes[node.id]);
    const placed = graph.node(node.id);
    return {
      ...node,
      position: stored
        ? { x: stored.x, y: stored.y }
        : { x: placed.x - placed.width / 2, y: placed.y - placed.height / 2 },
    };
  });
}

export function snapshot(nodes: TableNode[]): LayoutValue {
  return {
    version: 1,
    nodes: Object.fromEntries(nodes.map((node) => [
      node.id,
      { x: node.position.x, y: node.position.y, collapsed: node.data.collapsed },
    ])),
  };
}

export function matchesTable(table: DatabaseTable, query: string): boolean {
  return table.name.toLowerCase().includes(query) ||
    table.columns.some((column) => column.name.toLowerCase().includes(query));
}

export function relationshipText(fk: DatabaseForeignKey): string {
  return `${fk.name}: ${fk.from_table}.${fk.from_column} → ${fk.to_table}.${fk.to_column}`;
}
