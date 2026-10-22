import type { DiagramSpec } from '../specs';

/** Tools → Convert: a spoken clip in, the same words in a saved voice out. */
const spec: DiagramSpec = {
  width: 920,
  height: 340,
  nodes: [
    { id: 'source', x: 10, y: 30, w: 150, h: 64, tone: 'ui' },
    { id: 'voice', x: 10, y: 150, w: 150, h: 64, tone: 'ui' },
    { id: 'api', x: 200, y: 90, w: 140, h: 64, tone: 'backend' },
    { id: 'asr', x: 380, y: 30, w: 150, h: 64, tone: 'engine' },
    { id: 'text', x: 570, y: 30, w: 150, h: 64, tone: 'backend' },
    { id: 'tts', x: 760, y: 26, w: 150, h: 72, tone: 'engine' },
    { id: 'stretch', x: 760, y: 170, w: 150, h: 64, tone: 'backend' },
    { id: 'mark', x: 570, y: 170, w: 150, h: 64, tone: 'backend' },
    { id: 'result', x: 380, y: 170, w: 150, h: 64, tone: 'ui' },
    { id: 'history', x: 570, y: 264, w: 150, h: 66, tone: 'data', shape: 'store' },
  ],
  edges: [
    { from: 'source', to: 'api' },
    { from: 'voice', to: 'api', id: 'profile' },
    { from: 'api', to: 'asr' },
    { from: 'asr', to: 'text', id: 'words' },
    { from: 'text', to: 'tts' },
    { from: 'tts', to: 'stretch', id: 'optional', dashed: true },
    { from: 'stretch', to: 'mark' },
    { from: 'mark', to: 'result' },
    { from: 'mark', to: 'history', id: 'saved' },
  ],
};

export default spec;
