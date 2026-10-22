import type { DiagramSpec } from '../specs';

/** The whole system: what runs on this computer, and what may run elsewhere. */
const spec: DiagramSpec = {
  width: 920,
  height: 470,
  groups: [
    { id: 'computer', x: 20, y: 20, w: 650, h: 440, tone: 'neutral' },
    { id: 'remote', x: 690, y: 20, w: 210, h: 220, tone: 'remote' },
    { id: 'internet', x: 690, y: 280, w: 210, h: 150, tone: 'neutral' },
  ],
  nodes: [
    { id: 'ui', x: 50, y: 60, w: 170, h: 56, tone: 'ui' },
    { id: 'main', x: 50, y: 170, w: 170, h: 56, tone: 'ui' },
    { id: 'api', x: 300, y: 90, w: 170, h: 64, tone: 'backend' },
    { id: 'queue', x: 300, y: 200, w: 170, h: 56, tone: 'backend' },
    { id: 'engines', x: 500, y: 180, w: 140, h: 56, tone: 'engine' },
    { id: 'sidecars', x: 500, y: 270, w: 140, h: 56, tone: 'engine' },
    { id: 'data', x: 60, y: 360, w: 170, h: 72, tone: 'data', shape: 'store' },
    { id: 'models', x: 300, y: 360, w: 170, h: 72, tone: 'data', shape: 'store' },
    { id: 'ray', x: 710, y: 60, w: 170, h: 56, tone: 'remote' },
    { id: 'modal', x: 710, y: 150, w: 170, h: 56, tone: 'remote' },
    { id: 'hf', x: 710, y: 330, w: 170, h: 56, tone: 'neutral' },
  ],
  edges: [
    { from: 'ui', to: 'api', id: 'http', both: true },
    { from: 'main', to: 'ui', id: 'ipc', both: true },
    { from: 'main', to: 'api', id: 'spawn', dashed: true },
    { from: 'api', to: 'queue', id: 'jobs' },
    { from: 'queue', to: 'engines' },
    { from: 'queue', to: 'sidecars', id: 'pipe' },
    { from: 'queue', to: 'ray', id: 'remotejobs', dashed: true, via: [[485, 150]] },
    { from: 'queue', to: 'modal', dashed: true, via: [[485, 150]] },
    { from: 'api', to: 'data', id: 'store', via: [[260, 122], [260, 396]] },
    { from: 'models', to: 'engines', id: 'load', dashed: true, via: [[485, 250]] },
    { from: 'hf', to: 'models', id: 'download', dashed: true },
  ],
};

export default spec;
