import type { DiagramSpec } from '../specs';

/** What a remote job carries off this computer, and what never leaves it. */
const spec: DiagramSpec = {
  width: 920,
  height: 360,
  groups: [
    { id: 'computer', x: 20, y: 20, w: 540, h: 320, tone: 'neutral' },
    { id: 'remote', x: 600, y: 20, w: 300, h: 190, tone: 'remote' },
    { id: 'internet', x: 600, y: 240, w: 300, h: 100, tone: 'neutral' },
  ],
  nodes: [
    { id: 'inputs', x: 45, y: 55, w: 200, h: 76, tone: 'data', shape: 'store' },
    { id: 'models', x: 45, y: 150, w: 200, h: 76, tone: 'data', shape: 'store' },
    { id: 'secrets', x: 45, y: 245, w: 200, h: 76, tone: 'data', shape: 'store' },
    { id: 'backend', x: 340, y: 110, w: 190, h: 64, tone: 'backend' },
    { id: 'job', x: 630, y: 80, w: 240, h: 64, tone: 'remote' },
    { id: 'hub', x: 630, y: 266, w: 240, h: 56, tone: 'neutral' },
  ],
  edges: [
    { from: 'inputs', to: 'backend' },
    { from: 'models', to: 'backend', id: 'gated', dashed: true },
    { from: 'secrets', to: 'backend', id: 'local', via: [[435, 283]] },
    { from: 'backend', to: 'job', id: 'exchange', both: true },
    { from: 'hub', to: 'job', id: 'weights', dashed: true },
  ],
};

export default spec;
