// Diagram geometry, shared by every language. Text comes from the chapter's
// diagram block (`text[id]` for each node, group and labelled edge), so a
// diagram is drawn once and translated like any other content.

export type DiagramTone = 'ui' | 'backend' | 'engine' | 'remote' | 'data' | 'neutral';

export interface DiagramNode {
  id: string;
  x: number;
  y: number;
  w: number;
  h: number;
  tone?: DiagramTone;
  /** "store" draws a data store (cylinder-like) instead of a box. */
  shape?: 'box' | 'store';
}

export interface DiagramGroup {
  id: string;
  x: number;
  y: number;
  w: number;
  h: number;
  tone?: DiagramTone;
}

export interface DiagramEdge {
  from: string;
  to: string;
  /** Set when the edge has a label (its text key). */
  id?: string;
  /** Bend points between the two nodes. */
  via?: [number, number][];
  dashed?: boolean;
  /** Arrowheads at both ends. */
  both?: boolean;
}

export interface DiagramSpec {
  width: number;
  height: number;
  groups?: DiagramGroup[];
  nodes: DiagramNode[];
  edges: DiagramEdge[];
}

export function diagramTextIds(spec: DiagramSpec): string[] {
  return [
    ...(spec.groups ?? []).map((group) => group.id),
    ...spec.nodes.map((node) => node.id),
    ...spec.edges.flatMap((edge) => (edge.id ? [edge.id] : [])),
  ];
}

const specModules = import.meta.glob<{ default: DiagramSpec }>('./specs/*.ts', { eager: true });

/** Every diagram, by file name: diagrams/specs/<id>.ts default-exports its spec. */
export const DIAGRAMS: Record<string, DiagramSpec> = Object.fromEntries(
  Object.entries(specModules).map(([path, module]) => [
    path.replace(/^.*\/(.+)\.ts$/, '$1'),
    module.default,
  ]),
);
