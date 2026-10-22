import type { DiagramSpec } from '../specs';

/** Voice cloning: from the reference clip to a take in Recent takes. */
const spec: DiagramSpec = {
  width: 920,
  height: 370,
  groups: [{ id: 'gpu', x: 560, y: 115, w: 180, h: 140, tone: 'remote' }],
  nodes: [
    { id: 'ref', x: 10, y: 20, w: 150, h: 60, tone: 'ui' },
    { id: 'asr', x: 10, y: 110, w: 150, h: 60, tone: 'engine' },
    { id: 'transcript', x: 10, y: 200, w: 150, h: 60, tone: 'ui' },
    { id: 'script', x: 10, y: 290, w: 150, h: 60, tone: 'ui' },
    { id: 'request', x: 210, y: 150, w: 150, h: 70, tone: 'backend' },
    { id: 'prepare', x: 390, y: 150, w: 140, h: 70, tone: 'backend' },
    { id: 'engine', x: 575, y: 150, w: 150, h: 70, tone: 'remote' },
    { id: 'watermark', x: 770, y: 150, w: 140, h: 70, tone: 'backend' },
    { id: 'history', x: 770, y: 270, w: 140, h: 80, tone: 'data', shape: 'store' },
    { id: 'play', x: 575, y: 280, w: 150, h: 60, tone: 'ui' },
  ],
  edges: [
    { from: 'ref', to: 'asr', id: 'auto', dashed: true },
    { from: 'asr', to: 'transcript', id: 'fills' },
    { from: 'ref', to: 'request' },
    { from: 'transcript', to: 'request' },
    { from: 'script', to: 'request' },
    { from: 'request', to: 'prepare' },
    { from: 'prepare', to: 'engine', id: 'job' },
    { from: 'engine', to: 'watermark', id: 'audio' },
    { from: 'watermark', to: 'history', id: 'saved' },
    { from: 'history', to: 'play' },
  ],
};

export default spec;
