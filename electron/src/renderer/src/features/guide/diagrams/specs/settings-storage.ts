import type { DiagramSpec } from '../specs';

/** Where a setting is saved, what can override it, and when it takes effect. */
const spec: DiagramSpec = {
  width: 920,
  height: 330,
  groups: [
    { id: 'app', x: 5, y: 5, w: 220, h: 320, tone: 'ui' },
    { id: 'backend', x: 245, y: 5, w: 445, h: 320, tone: 'backend' },
    { id: 'apply', x: 710, y: 5, w: 205, h: 320, tone: 'neutral' },
  ],
  nodes: [
    { id: 'ui', x: 25, y: 45, w: 180, h: 64, tone: 'ui' },
    { id: 'local', x: 25, y: 215, w: 180, h: 72, tone: 'data', shape: 'store' },
    { id: 'api', x: 265, y: 45, w: 160, h: 64, tone: 'backend' },
    { id: 'env', x: 265, y: 215, w: 160, h: 72, tone: 'neutral' },
    { id: 'prefs', x: 480, y: 35, w: 190, h: 64, tone: 'data', shape: 'store' },
    { id: 'table', x: 480, y: 135, w: 190, h: 64, tone: 'data', shape: 'store' },
    { id: 'secrets', x: 480, y: 235, w: 190, h: 64, tone: 'data', shape: 'store' },
    { id: 'now', x: 725, y: 60, w: 175, h: 64, tone: 'engine' },
    { id: 'restart', x: 725, y: 215, w: 175, h: 72, tone: 'neutral' },
  ],
  edges: [
    { from: 'ui', to: 'local', id: 'instant' },
    { from: 'ui', to: 'api', id: 'http' },
    { from: 'api', to: 'prefs' },
    { from: 'api', to: 'table' },
    { from: 'api', to: 'secrets' },
    { from: 'env', to: 'api', id: 'overrides' },
    { from: 'prefs', to: 'now' },
    { from: 'table', to: 'now' },
    { from: 'secrets', to: 'now' },
    { from: 'now', to: 'restart', id: 'some', dashed: true },
  ],
};

export default spec;
