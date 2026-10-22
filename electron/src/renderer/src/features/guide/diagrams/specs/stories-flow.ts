import type { DiagramSpec } from '../specs';

/** Stories: from a script to one stitched file, through the shared longform renderer. */
const spec: DiagramSpec = {
  width: 920,
  height: 350,
  nodes: [
    { id: 'script', x: 10, y: 40, w: 160, h: 80, tone: 'ui' },
    { id: 'lines', x: 220, y: 40, w: 160, h: 80, tone: 'ui' },
    { id: 'voices', x: 430, y: 40, w: 180, h: 80, tone: 'ui' },
    { id: 'plan', x: 660, y: 40, w: 250, h: 80, tone: 'backend' },
    { id: 'out', x: 10, y: 210, w: 150, h: 84, tone: 'ui' },
    { id: 'mux', x: 200, y: 210, w: 180, h: 84, tone: 'backend' },
    { id: 'chapter', x: 420, y: 210, w: 150, h: 84, tone: 'backend' },
    { id: 'batch', x: 610, y: 210, w: 160, h: 84, tone: 'remote' },
    { id: 'cache', x: 800, y: 206, w: 110, h: 92, tone: 'data', shape: 'store' },
  ],
  edges: [
    { from: 'script', to: 'lines' },
    { from: 'lines', to: 'voices' },
    { from: 'voices', to: 'plan' },
    { from: 'plan', to: 'cache', id: 'lookup' },
    { from: 'plan', to: 'batch', id: 'missing' },
    { from: 'cache', to: 'chapter', id: 'hit', dashed: true, via: [[855, 330], [495, 330]] },
    { from: 'batch', to: 'chapter' },
    { from: 'chapter', to: 'mux' },
    { from: 'mux', to: 'out' },
  ],
};

export default spec;
