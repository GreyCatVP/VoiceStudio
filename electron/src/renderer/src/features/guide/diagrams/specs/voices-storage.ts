import type { DiagramSpec } from '../specs';

/** Where a saved voice comes from, where it is stored and who uses it. */
const spec: DiagramSpec = {
  width: 920,
  height: 380,
  groups: [{ id: 'data', x: 380, y: 20, w: 200, h: 340, tone: 'data' }],
  nodes: [
    { id: 'clone', x: 10, y: 20, w: 160, h: 56, tone: 'ui' },
    { id: 'design', x: 10, y: 100, w: 160, h: 56, tone: 'ui' },
    { id: 'gallery', x: 10, y: 180, w: 160, h: 56, tone: 'ui' },
    { id: 'import', x: 10, y: 260, w: 160, h: 56, tone: 'ui' },
    { id: 'api', x: 205, y: 140, w: 140, h: 70, tone: 'backend' },
    { id: 'db', x: 400, y: 70, w: 160, h: 90, tone: 'data', shape: 'store' },
    { id: 'files', x: 400, y: 210, w: 160, h: 90, tone: 'data', shape: 'store' },
    { id: 'workspaces', x: 640, y: 40, w: 270, h: 70, tone: 'ui' },
    { id: 'long', x: 640, y: 140, w: 270, h: 70, tone: 'ui' },
    { id: 'export', x: 640, y: 250, w: 270, h: 70, tone: 'neutral' },
  ],
  edges: [
    { from: 'clone', to: 'api' },
    { from: 'design', to: 'api' },
    { from: 'gallery', to: 'api' },
    { from: 'import', to: 'api' },
    { from: 'api', to: 'db', id: 'row' },
    { from: 'api', to: 'files', id: 'clip' },
    { from: 'db', to: 'workspaces', id: 'pick' },
    { from: 'db', to: 'long' },
    { from: 'files', to: 'export', id: 'bundle', dashed: true },
  ],
};

export default spec;
