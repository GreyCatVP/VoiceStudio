import type { DiagramSpec } from '../specs';

/** Voice design: from a description to a take and a saved design voice. */
const spec: DiagramSpec = {
  width: 920,
  height: 330,
  groups: [{ id: 'gpu', x: 560, y: 60, w: 180, h: 140, tone: 'remote' }],
  nodes: [
    { id: 'describe', x: 10, y: 20, w: 150, h: 64, tone: 'ui' },
    { id: 'presets', x: 10, y: 130, w: 150, h: 64, tone: 'ui' },
    { id: 'mapper', x: 200, y: 20, w: 150, h: 64, tone: 'backend' },
    { id: 'details', x: 385, y: 95, w: 145, h: 80, tone: 'ui' },
    { id: 'script', x: 575, y: 245, w: 150, h: 56, tone: 'ui' },
    { id: 'engine', x: 575, y: 95, w: 150, h: 80, tone: 'remote' },
    { id: 'history', x: 770, y: 95, w: 140, h: 80, tone: 'data', shape: 'store' },
    { id: 'profile', x: 385, y: 235, w: 145, h: 80, tone: 'data', shape: 'store' },
  ],
  edges: [
    { from: 'describe', to: 'mapper' },
    { from: 'mapper', to: 'details', id: 'fills' },
    { from: 'presets', to: 'details' },
    { from: 'details', to: 'engine', id: 'instruct' },
    { from: 'script', to: 'engine' },
    { from: 'engine', to: 'history', id: 'saved' },
    { from: 'details', to: 'profile', id: 'save', dashed: true },
  ],
};

export default spec;
