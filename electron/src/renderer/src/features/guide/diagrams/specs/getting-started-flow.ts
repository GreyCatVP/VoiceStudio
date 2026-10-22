import type { DiagramSpec } from '../specs';

/** First run (top) and what happens when you install a model (bottom). */
const spec: DiagramSpec = {
  width: 920,
  height: 360,
  groups: [
    { id: 'firstrun', x: 5, y: 5, w: 910, h: 110, tone: 'ui' },
    { id: 'install', x: 5, y: 135, w: 910, h: 215, tone: 'backend' },
  ],
  nodes: [
    { id: 'check', x: 25, y: 38, w: 180, h: 60, tone: 'ui' },
    { id: 'packs', x: 255, y: 38, w: 180, h: 60, tone: 'ui' },
    { id: 'privacy', x: 485, y: 38, w: 180, h: 60, tone: 'ui' },
    { id: 'studio', x: 715, y: 38, w: 180, h: 60, tone: 'ui' },
    { id: 'pick', x: 25, y: 175, w: 130, h: 72, tone: 'ui' },
    { id: 'backend', x: 255, y: 175, w: 160, h: 72, tone: 'backend' },
    { id: 'hub', x: 505, y: 175, w: 130, h: 72, tone: 'remote' },
    { id: 'cache', x: 715, y: 175, w: 180, h: 72, tone: 'data', shape: 'store' },
    { id: 'progress', x: 255, y: 280, w: 160, h: 56, tone: 'neutral' },
    { id: 'licence', x: 505, y: 280, w: 130, h: 56, tone: 'ui' },
    { id: 'ready', x: 715, y: 280, w: 180, h: 56, tone: 'engine' },
  ],
  edges: [
    { from: 'check', to: 'packs' },
    { from: 'packs', to: 'privacy' },
    { from: 'privacy', to: 'studio' },
    { from: 'packs', to: 'pick', id: 'starts', via: [[345, 150], [90, 150]] },
    { from: 'pick', to: 'backend', id: 'request' },
    { from: 'backend', to: 'hub', id: 'download' },
    { from: 'hub', to: 'cache', id: 'files' },
    { from: 'cache', to: 'ready' },
    { from: 'licence', to: 'ready', id: 'ifneeded', dashed: true },
    { from: 'backend', to: 'progress', id: 'events', dashed: true },
    { from: 'progress', to: 'pick', dashed: true, via: [[90, 308]] },
  ],
};

export default spec;
