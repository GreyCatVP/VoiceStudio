import type { DiagramSpec } from '../specs';

/** One generation, from the text box to the finished audio. */
const spec: DiagramSpec = {
  width: 920,
  height: 260,
  nodes: [
    { id: 'type', x: 5, y: 40, w: 130, h: 76, tone: 'ui' },
    { id: 'request', x: 161, y: 40, w: 130, h: 76, tone: 'backend' },
    { id: 'route', x: 317, y: 40, w: 130, h: 76, tone: 'backend' },
    { id: 'render', x: 473, y: 40, w: 130, h: 76, tone: 'engine' },
    { id: 'finish', x: 629, y: 40, w: 130, h: 76, tone: 'backend' },
    { id: 'play', x: 785, y: 40, w: 130, h: 76, tone: 'ui' },
    { id: 'history', x: 629, y: 170, w: 130, h: 72, tone: 'data', shape: 'store' },
    { id: 'progress', x: 161, y: 178, w: 286, h: 56, tone: 'neutral' },
  ],
  edges: [
    { from: 'type', to: 'request' },
    { from: 'request', to: 'route' },
    { from: 'route', to: 'render' },
    { from: 'render', to: 'finish' },
    { from: 'finish', to: 'play' },
    { from: 'finish', to: 'history', id: 'saved' },
    { from: 'route', to: 'progress', id: 'events', dashed: true },
    { from: 'progress', to: 'type', dashed: true, via: [[70, 206]] },
  ],
};

export default spec;
