import type { DiagramSpec } from '../specs';

/** What the Projects library lists, and where each kind of item is stored. */
const spec: DiagramSpec = {
  width: 920,
  height: 360,
  groups: [
    { id: 'app', x: 20, y: 110, w: 420, h: 230, tone: 'ui' },
    { id: 'backend', x: 480, y: 110, w: 420, h: 230, tone: 'data' },
  ],
  nodes: [
    { id: 'page', x: 330, y: 16, w: 260, h: 56, tone: 'ui' },
    { id: 'longform', x: 40, y: 150, w: 180, h: 72, tone: 'data', shape: 'store' },
    { id: 'transcripts', x: 240, y: 150, w: 180, h: 72, tone: 'data', shape: 'store' },
    { id: 'workspaces', x: 40, y: 254, w: 380, h: 64, tone: 'ui' },
    { id: 'dubs', x: 500, y: 150, w: 180, h: 72, tone: 'data', shape: 'store' },
    { id: 'voices', x: 700, y: 150, w: 180, h: 72, tone: 'data', shape: 'store' },
    { id: 'history', x: 500, y: 250, w: 180, h: 72, tone: 'data', shape: 'store' },
    { id: 'exports', x: 700, y: 250, w: 180, h: 72, tone: 'data', shape: 'store' },
  ],
  edges: [
    // One bus from the library to every store it lists.
    { from: 'page', to: 'longform', via: [[460, 94], [130, 94]] },
    { from: 'page', to: 'transcripts', via: [[460, 94], [330, 94]] },
    { from: 'page', to: 'dubs', via: [[460, 94], [590, 94]] },
    { from: 'page', to: 'voices', via: [[460, 94], [790, 94]] },
    { from: 'page', to: 'history', via: [[460, 94], [460, 286]] },
    { from: 'page', to: 'exports', via: [[460, 94], [895, 94], [895, 286]] },
    { from: 'longform', to: 'workspaces', id: 'open', dashed: true },
  ],
};

export default spec;
