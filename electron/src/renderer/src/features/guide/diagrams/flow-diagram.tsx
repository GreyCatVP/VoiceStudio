import { useId } from 'react';
import { cn } from '@/lib/utils';
import type { DiagramNode, DiagramSpec, DiagramTone } from './specs';

const TONES: Record<DiagramTone, { box: string; group: string }> = {
  ui: { box: 'fill-sky-500/12 stroke-sky-500/70', group: 'fill-sky-500/[0.04] stroke-sky-500/35' },
  backend: {
    box: 'fill-violet-500/12 stroke-violet-500/70',
    group: 'fill-violet-500/[0.04] stroke-violet-500/35',
  },
  engine: {
    box: 'fill-amber-500/12 stroke-amber-500/70',
    group: 'fill-amber-500/[0.04] stroke-amber-500/35',
  },
  remote: {
    box: 'fill-emerald-500/12 stroke-emerald-500/70',
    group: 'fill-emerald-500/[0.04] stroke-emerald-500/35',
  },
  data: { box: 'fill-rose-500/12 stroke-rose-500/70', group: 'fill-rose-500/[0.04] stroke-rose-500/35' },
  neutral: { box: 'fill-muted stroke-border', group: 'fill-muted/30 stroke-border' },
};

type Point = [number, number];

const center = (node: DiagramNode): Point => [node.x + node.w / 2, node.y + node.h / 2];

/** Where the line from the node's centre toward `toward` leaves its box. */
function anchor(node: DiagramNode, toward: Point): Point {
  const [cx, cy] = center(node);
  const dx = toward[0] - cx;
  const dy = toward[1] - cy;
  if (dx === 0 && dy === 0) return [cx, cy];
  const scale = Math.min(
    dx === 0 ? Infinity : node.w / 2 / Math.abs(dx),
    dy === 0 ? Infinity : node.h / 2 / Math.abs(dy),
  );
  return [cx + dx * scale, cy + dy * scale];
}

function edgePoints(from: DiagramNode, to: DiagramNode, via: Point[] = []): Point[] {
  const first = via[0] ?? center(to);
  const last = via[via.length - 1] ?? center(from);
  return [anchor(from, first), ...via, anchor(to, last)];
}

/** Midpoint of the longest segment: where a label is least likely to collide. */
function labelPoint(points: Point[]): Point {
  let best: Point = points[0];
  let length = -1;
  for (let i = 1; i < points.length; i += 1) {
    const [ax, ay] = points[i - 1];
    const [bx, by] = points[i];
    const segment = Math.hypot(bx - ax, by - ay);
    if (segment > length) {
      length = segment;
      best = [(ax + bx) / 2, (ay + by) / 2];
    }
  }
  return best;
}

function Lines({ text, x, y, className }: { text: string; x: number; y: number; className: string }) {
  const lines = text.split('\n');
  const lineHeight = 17;
  const top = y - ((lines.length - 1) * lineHeight) / 2;
  return (
    <text className={className} textAnchor="middle" dominantBaseline="central">
      {lines.map((line, index) => (
        <tspan key={index} x={x} y={top + index * lineHeight}>
          {line}
        </tspan>
      ))}
    </text>
  );
}

export function FlowDiagram({
  spec,
  text,
  label,
}: {
  spec: DiagramSpec;
  text: Record<string, string>;
  label: string;
}) {
  const marker = useId().replace(/:/g, '');
  const nodes = new Map(spec.nodes.map((node) => [node.id, node]));
  return (
    <div className="overflow-x-auto">
      <svg
        role="img"
        aria-label={label}
        viewBox={`0 0 ${spec.width} ${spec.height}`}
        className="h-auto w-full min-w-[640px] text-[14px]"
        style={{ maxWidth: spec.width }}
      >
        <defs>
          <marker
            id={`${marker}-arrow`}
            viewBox="0 0 10 10"
            refX="9"
            refY="5"
            markerWidth="7"
            markerHeight="7"
            orient="auto-start-reverse"
          >
            <path d="M0,0 L10,5 L0,10 z" className="fill-muted-foreground" />
          </marker>
        </defs>
        {(spec.groups ?? []).map((group) => (
          <g key={group.id}>
            <rect
              x={group.x}
              y={group.y}
              width={group.w}
              height={group.h}
              rx={14}
              strokeDasharray="5 4"
              className={TONES[group.tone ?? 'neutral'].group}
            />
            <text x={group.x + 12} y={group.y + 18} className="fill-muted-foreground text-[13px] font-medium">
              {text[group.id] ?? group.id}
            </text>
          </g>
        ))}
        {spec.edges.map((edge, index) => {
          const from = nodes.get(edge.from);
          const to = nodes.get(edge.to);
          if (!from || !to) return null;
          const points = edgePoints(from, to, edge.via);
          const at = edge.id ? labelPoint(points) : null;
          return (
            <g key={`${edge.from}-${edge.to}-${index}`}>
              <polyline
                points={points.map((point) => point.join(',')).join(' ')}
                fill="none"
                strokeWidth={1.5}
                strokeDasharray={edge.dashed ? '5 4' : undefined}
                markerEnd={`url(#${marker}-arrow)`}
                markerStart={edge.both ? `url(#${marker}-arrow)` : undefined}
                className="stroke-muted-foreground"
              />
              {at && edge.id && (
                <Lines
                  text={text[edge.id] ?? edge.id}
                  x={at[0]}
                  y={at[1]}
                  className="fill-foreground text-[12.5px] [paint-order:stroke] [stroke-linejoin:round] stroke-background [stroke-width:5px]"
                />
              )}
            </g>
          );
        })}
        {spec.nodes.map((node) => {
          const [cx, cy] = center(node);
          const tone = TONES[node.tone ?? 'neutral'].box;
          return (
            <g key={node.id}>
              {node.shape === 'store' ? (
                <>
                  <rect x={node.x} y={node.y + 6} width={node.w} height={node.h - 6} className={tone} />
                  <ellipse cx={cx} cy={node.y + 6} rx={node.w / 2} ry={6} className={tone} />
                </>
              ) : (
                <rect x={node.x} y={node.y} width={node.w} height={node.h} rx={10} className={tone} />
              )}
              <Lines
                text={text[node.id] ?? node.id}
                x={cx}
                y={node.shape === 'store' ? cy + 3 : cy}
                className={cn('fill-foreground', 'font-medium')}
              />
            </g>
          );
        })}
      </svg>
    </div>
  );
}
