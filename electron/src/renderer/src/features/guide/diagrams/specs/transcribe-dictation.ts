import type { DiagramSpec } from '../specs';

/** The dictation loop: shortcut, microphone, live transcription, typed text. */
const spec: DiagramSpec = {
  width: 920,
  height: 260,
  nodes: [
    { id: 'key', x: 5, y: 30, w: 140, h: 64, tone: 'ui' },
    { id: 'helper', x: 175, y: 30, w: 140, h: 64, tone: 'ui' },
    { id: 'mic', x: 345, y: 30, w: 140, h: 64, tone: 'ui' },
    { id: 'ws', x: 515, y: 30, w: 150, h: 64, tone: 'backend' },
    { id: 'model', x: 700, y: 30, w: 210, h: 64, tone: 'engine' },
    { id: 'stop', x: 5, y: 170, w: 140, h: 64, tone: 'ui' },
    { id: 'history', x: 290, y: 170, w: 140, h: 72, tone: 'data', shape: 'store' },
    { id: 'clip', x: 470, y: 170, w: 150, h: 64, tone: 'neutral' },
    { id: 'deliver', x: 700, y: 170, w: 210, h: 64, tone: 'ui' },
  ],
  edges: [
    { from: 'key', to: 'helper' },
    { from: 'helper', to: 'mic' },
    { from: 'mic', to: 'ws' },
    { from: 'ws', to: 'model' },
    { from: 'model', to: 'deliver', id: 'text' },
    { from: 'deliver', to: 'clip', id: 'fallback', dashed: true },
    { from: 'model', to: 'history', id: 'saved', via: [[760, 150], [360, 150]] },
    { from: 'stop', to: 'mic', id: 'eof', dashed: true, via: [[75, 135], [415, 135]] },
  ],
};

export default spec;
